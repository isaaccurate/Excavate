import type { Citation } from "./api";
import { excerptOf, wikilinkTarget } from "./citations";
import { RichText } from "./RichText";

function Source({ citation }: { citation: Citation }) {
  const target = wikilinkTarget(citation);
  const excerpt = excerptOf(citation);
  return (
    <details className="source">
      <summary className="source__summary">
        <span className="source__marker" aria-hidden="true" />
        <span className="source__link">
          <span className="source__bracket" aria-hidden="true">
            [[
          </span>
          {target}
          <span className="source__bracket" aria-hidden="true">
            ]]
          </span>
        </span>
      </summary>
      <div className="source__body">
        <p className="source__path">{citation.path}</p>
        {citation.heading.length > 0 ? (
          <ol className="trail" aria-label="Heading trail">
            {citation.heading.map((part, depth) => (
              <li className="trail__heading" key={`${depth}-${part}`}>
                {Array.from({ length: depth }, (_, guide) => (
                  <span className="trail__guide" aria-hidden="true" key={guide} />
                ))}
                <span className="trail__text">{part}</span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="source__note">Cited from the text above the first heading.</p>
        )}
        {excerpt !== null ? (
          <blockquote className="source__excerpt" aria-label="Cited excerpt">
            <RichText text={excerpt} keepLineBreaks />
          </blockquote>
        ) : null}
      </div>
    </details>
  );
}

export function Sources({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null;
  return (
    <section className="sources" aria-label="Cited sections">
      <h2 className="sources__title">
        {citations.length === 1 ? "1 section" : `${citations.length} sections`} behind
        this answer
      </h2>
      <div className="sources__list">
        {citations.map((citation) => (
          <Source citation={citation} key={citation.id} />
        ))}
      </div>
    </section>
  );
}
