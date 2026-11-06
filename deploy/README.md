# AWS deployment

This stack uses an existing private, unversioned S3 bucket and DynamoDB table. It runs FastAPI behind an IAM-authenticated Lambda Function URL and runs retention cleanup in a separate Lambda. Both functions use the same Linux image and separate execution roles. The stack does not own the note bucket or table.

## Build the image

Set `DOCUMENT_BUCKET` to the full existing bucket name and `DOCUMENT_TABLE` to the table name. Sign in with `aws login --profile excavate` and confirm the AWS project has sufficient credits in AWS Settings → Billing.

```sh
export AWS_PROFILE=excavate AWS_DEFAULT_REGION=us-east-2
export DOCUMENT_BUCKET=YOUR_FULL_BUCKET_NAME DOCUMENT_TABLE=excavate-smoke

aws cloudformation deploy --stack-name excavate-image-build \
  --template-file deploy/build.yaml --capabilities CAPABILITY_IAM \
  --parameter-overrides "SourceBucket=$DOCUMENT_BUCKET"
```

From the repository root, archive only the deployment source. CodeBuild reads the archive under `build-source/` and pushes an immutable tag to ECR. The build verifies that FAISS and the Lambda handlers import and SQLite can create an FTS5 table.

```sh
build_dir=$(mktemp -d)
source_archive="$build_dir/source.zip"
zip -q "$source_archive" pyproject.toml .dockerignore deploy/Dockerfile \
  deploy/buildspec.yaml knowledge_assistant/*.py
image_tag="build-$(shasum -a 256 "$source_archive" | cut -c1-20)"
source_key="build-source/$image_tag.zip"
aws s3 cp "$source_archive" "s3://$DOCUMENT_BUCKET/$source_key"
build_id=$(aws codebuild start-build --project-name excavate-image-build \
  --source-location-override "$DOCUMENT_BUCKET/$source_key" \
  --environment-variables-override "name=IMAGE_TAG,value=$image_tag,type=PLAINTEXT" \
  --query build.id --output text)
aws codebuild batch-get-builds --ids "$build_id" \
  --query 'builds[0].{Status:buildStatus,Logs:logs.deepLink}'
```

Once the build reports `SUCCEEDED`, remove the source archive and resolve the immutable image URI.

```sh
aws s3api delete-object --bucket "$DOCUMENT_BUCKET" --key "$source_key"
rm "$source_archive"
rmdir "$build_dir"
repository=$(aws ecr describe-repositories --repository-names excavate-image-build \
  --query 'repositories[0].repositoryUri' --output text)
digest=$(aws ecr describe-images --repository-name excavate-image-build \
  --image-ids "imageTag=$image_tag" --query 'imageDetails[0].imageDigest' --output text)
image_uri="$repository@$digest"
```

## Deploy and verify

```sh
aws cloudformation deploy --stack-name excavate-smoke-app \
  --template-file deploy/template.yaml --capabilities CAPABILITY_IAM \
  --parameter-overrides "ImageUri=$image_uri" "DocumentBucket=$DOCUMENT_BUCKET" \
    "DocumentTable=$DOCUMENT_TABLE" ScheduleState=DISABLED
aws cloudformation describe-stacks --stack-name excavate-smoke-app \
  --query 'Stacks[0].Outputs'
```

Use a SigV4-signed request for `GET /health`. A signed request should return 200, and an unsigned request should return 403. With synthetic notes in the test table, invoke the cleanup function and confirm it removes only expired records and their tracked objects. Once verified, repeat the deploy command with `ScheduleState=ENABLED`.

For live answers, create a Secrets Manager secret in Ohio whose secret string is the OpenAI API key. Redeploy with `OpenAISecretArn` and `OpenAIModel` together. The API reads only the configured secret. Test `POST /answer` with synthetic evidence before migrating real notes. Ingestion and restore continue to run through the CLI.

Deploying can use Free Tier credits or incur usage charges depending on the AWS project plan. The hourly schedule and retained ECR image persist between tests. Check AWS Settings → Billing for remaining credits. Separate OpenAI usage applies when live answers are enabled.
