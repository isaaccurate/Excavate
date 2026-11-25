# AWS deployment

Excavate runs on AWS Lambda behind an IAM-authenticated Function URL. It uses an existing private, unversioned S3 bucket and DynamoDB table. Set up storage and ingest notes using the [usage guide](../docs/usage.md#manage-notes-in-aws).

Run the commands from the repository root in one terminal session; later steps reuse its variables. You need `zip`, the AWS CLI v2 signed in to a profile (for example with `aws login --profile YOUR_PROFILE`), and permission to create CloudFormation stacks with IAM roles, ECR, CodeBuild, Lambda, EventBridge Scheduler, and Secrets Manager resources. Calling the API also needs `lambda:InvokeFunctionUrl` and `lambda:InvokeFunction`. Set these values to match your storage.

```sh
export AWS_PROFILE=YOUR_PROFILE AWS_DEFAULT_REGION=YOUR_REGION
export DOCUMENT_BUCKET=YOUR_BUCKET DOCUMENT_TABLE=YOUR_TABLE
```

## Build the backend image

If the backend version you want is already in ECR, set `image_uri` to its `repository@sha256:…` URI and continue to [Deploy the API](#deploy-the-api). CloudFormation template edits can reuse the current image.

Create or update the CodeBuild project and ECR repository.

```sh
aws cloudformation deploy --stack-name excavate-image-build \
  --template-file deploy/build.yaml --capabilities CAPABILITY_IAM \
  --parameter-overrides "SourceBucket=$DOCUMENT_BUCKET"
```

Package the backend source. The image tag is derived from this archive.

```sh
build_dir=$(mktemp -d)
source_archive="$build_dir/source.zip"
zip -q "$source_archive" pyproject.toml .dockerignore deploy/Dockerfile \
  deploy/buildspec.yaml knowledge_assistant/*.py
image_tag="build-$(shasum -a 256 "$source_archive" | cut -c1-20)"
printf '%s\n' "$image_tag"
```

ECR tags are immutable, so building unchanged source again fails. Check for the tag with `aws ecr describe-images --repository-name excavate-image-build --image-ids "imageTag=$image_tag"`. If it exists, skip the upload and build and continue with the digest lookup. Otherwise, upload the archive and start CodeBuild.

```sh
source_key="build-source/$image_tag.zip"
aws s3 cp "$source_archive" "s3://$DOCUMENT_BUCKET/$source_key"
build_id=$(aws codebuild start-build --project-name excavate-image-build \
  --source-location-override "$DOCUMENT_BUCKET/$source_key" \
  --environment-variables-override "name=IMAGE_TAG,value=$image_tag,type=PLAINTEXT" \
  --query build.id --output text)
aws codebuild batch-get-builds --ids "$build_id" \
  --query 'builds[0].{Status:buildStatus,Logs:logs.deepLink}'
```

Re-run `batch-get-builds` until it reports `SUCCEEDED`. Then remove the uploaded archive with `aws s3api delete-object --bucket "$DOCUMENT_BUCKET" --key "$source_key"`. Look up the image digest that Lambda will run.

```sh
rm "$source_archive"
rmdir "$build_dir"
repository=$(aws ecr describe-repositories --repository-names excavate-image-build \
  --query 'repositories[0].repositoryUri' --output text)
digest=$(aws ecr describe-images --repository-name excavate-image-build \
  --image-ids "imageTag=$image_tag" --query 'imageDetails[0].imageDigest' --output text)
image_uri="$repository@$digest"
```

## Deploy the API

Choose a stack name and an answer model. Use a Secrets Manager secret in the same region whose value is the raw provider API key; create it once with `aws secretsmanager create-secret --name YOUR_SECRET_NAME --secret-string "$OPENAI_API_KEY"`. Set the embedding model to match ingestion, or leave it blank to use local token-hash vectors.

```sh
stack_name=excavate-app
answer_model=YOUR_ANSWER_MODEL
embedding_model=text-embedding-3-small
secret_arn=$(aws secretsmanager describe-secret --secret-id YOUR_SECRET_NAME \
  --query ARN --output text) &&
aws cloudformation deploy --stack-name "$stack_name" \
  --template-file deploy/template.yaml --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    "ImageUri=$image_uri" "DocumentBucket=$DOCUMENT_BUCKET" \
    "DocumentTable=$DOCUMENT_TABLE" "OpenAISecretArn=$secret_arn" \
    "OpenAIModel=$answer_model" "EmbeddingModel=$embedding_model" \
    ScheduleState=DISABLED
```

Get the URL for the deployed API.

```sh
api_url=$(aws cloudformation describe-stacks --stack-name "$stack_name" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue | [0]" \
  --output text)
api_url=${api_url%/}
printf '%s\n' "$api_url"
```

## Verify the deployment

An unsigned request should return 403. Signed requests use your profile's credentials with [SigV4](https://docs.aws.amazon.com/lambda/latest/dg/urls-invocation.html); curl 7.75 or later can sign them.

```sh
curl -s -o /dev/null -w '%{http_code}\n' "$api_url/health"
eval "$(aws configure export-credentials --format env)"
sign=(--aws-sigv4 "aws:amz:$AWS_DEFAULT_REGION:lambda"
  --user "$AWS_ACCESS_KEY_ID:$AWS_SECRET_ACCESS_KEY")
[ -n "${AWS_SESSION_TOKEN:-}" ] && sign+=(-H "x-amz-security-token: $AWS_SESSION_TOKEN")
curl "${sign[@]}" "$api_url/health"
curl "${sign[@]}" "$api_url/answer" -H 'Content-Type: application/json' \
  -d '{"question":"YOUR_QUESTION"}'
aws lambda invoke --function-name "$stack_name-cleanup" /dev/stdout
```

- Ask `POST /answer` a question the notes cover and one they cannot answer. Check that the first returns a cited excerpt and the second returns `insufficient_evidence`.
- The cleanup function should return `{"purged_notes": N}` without an error. After verifying it on test notes, redeploy with `ScheduleState=ENABLED` to remove expired copies hourly under the [seven-day retention policy](../docs/usage.md#manage-notes-in-aws).
- To connect the React frontend, route `/answer` through a backend that signs requests to Lambda. Keep AWS credentials on that backend. See the [frontend guide](../frontend/README.md).

## Remove the deployment

Delete the API stack before the build stack. The ECR repository is retained when its stack is deleted, so remove it separately. The notes bucket and table are not part of either stack.

```sh
aws cloudformation delete-stack --stack-name "$stack_name"
aws cloudformation wait stack-delete-complete --stack-name "$stack_name"
aws cloudformation delete-stack --stack-name excavate-image-build
aws cloudformation wait stack-delete-complete --stack-name excavate-image-build
aws ecr delete-repository --repository-name excavate-image-build --force
aws secretsmanager delete-secret --secret-id YOUR_SECRET_NAME
```

Until removed, the hourly schedule, stored images, secret, and storage can incur AWS charges. OpenAI usage is billed separately.
