import type { Citation } from "./api";
import { RichText } from "./RichText";
import { Sources } from "./Sources";

export default function AnswerContent({ answer, citations }: { answer: string; citations: Citation[] }) {
  return (
    <>
      <RichText className="reply__answer" text={answer} />
      <Sources citations={citations} />
    </>
  );
}
