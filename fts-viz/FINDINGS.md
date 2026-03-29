# FTS Visualization Exploration: Research Findings

## What Users Searching Across Texts Care About

When a user searches across a corpus of texts ranging from tens of words (short
notes, metadata) to thousands of words (articles, documents, reports), their
needs fall into several layers:

### Layer 1: "Did it match?" (Basic Relevance)

- **Which documents matched** — the most fundamental need
- **How many matched** — scope of results
- **Relevance ranking** — which matches are strongest (BM25 scores)
- **Match count per document** — term frequency signal

Users at this level just need a fast answer: "where is this term?"

### Layer 2: "What does it say?" (Context & Snippets)

- **Surrounding context** — seeing the match in its sentence/paragraph
- **Highlighted terms** — visually distinguishing matched words from context
- **Multiple snippets per document** — when a term appears in several places
- **Document metadata** — title, length, date, category

Users here want to evaluate whether a match is actually relevant without
opening the full document. The snippet is the key unit of information.

### Layer 3: "How well does it match?" (Quantitative Signals)

- **BM25 score breakdown** — not just "it matched" but "how well"
- **Term frequency (TF)** — how many times do search terms appear
- **Document frequency (DF)** — how common are these terms across the corpus
- **Coverage** — does the document contain ALL search terms or just some
- **Match density** — are matches clustered or spread throughout

Users at this level are doing comparative analysis: "which of these 20 results
is actually most relevant to my query?"

### Layer 4: "What's the landscape?" (Corpus-Level Insight)

- **Term distribution across documents** — heat map / coverage matrix
- **Term co-occurrence** — which search terms tend to appear together
- **Document similarity** — based on shared term profiles
- **Position distribution** — where in documents do matches tend to occur
  (beginning, middle, end — useful for long documents)
- **Relative term importance** — which of my search terms is most
  discriminating (appears in fewer documents)

Users at this level are doing research or analysis. They want to understand
the *shape* of their query's relationship to the corpus.

---

## Visualization Matrix

Two independent axes:

### Axis 1: Insight Depth (Simple → Insightful)

| Level     | What's shown                                         |
|-----------|------------------------------------------------------|
| Simple    | Ranked list of document names + scores               |
| Moderate  | Snippets with highlighted matches, match counts      |
| Insightful| Term analytics, coverage matrix, position sparklines |

### Axis 2: Visual Style (Plain → Fancy)

| Level  | How it looks                                              |
|--------|-----------------------------------------------------------|
| Plain  | Monochrome, minimal borders, raw numbers                  |
| Fancy  | Color-coded relevance, gradient bars, styled borders      |

This gives us a 3x2 matrix of 6 visualization modes:

```
                    Plain                   Fancy
              ┌─────────────────┬──────────────────────┐
  Simple      │ 1. Ranked list  │ 2. Styled list with  │
              │    mono, sparse │    color score bars   │
              ├─────────────────┼──────────────────────┤
  Moderate    │ 3. Snippets,    │ 4. Rich snippets,    │
              │    basic markup │    relevance meters   │
              ├─────────────────┼──────────────────────┤
  Insightful  │ 5. ASCII tables │ 6. Sparklines, heat  │
              │    freq counts  │    maps, deep stats   │
              └─────────────────┴──────────────────────┘
```

---

## Implementation Notes

- **SQLite FTS5** provides: `bm25()`, `highlight()`, `snippet()`, `rank`
- **Bubble Tea** provides: TUI framework with model/update/view pattern
- **Lip Gloss** provides: styling (colors, borders, padding, alignment)
- **Bubbles** provides: pre-built components (text input, viewport, table)
- **VHS** provides: deterministic terminal recording → GIF/PNG

### FTS5 Functions Used Per Visualization Level

| Level      | FTS5 Functions                                       |
|------------|------------------------------------------------------|
| Simple     | `rank`, `bm25()`                                     |
| Moderate   | `snippet()`, `highlight()`, match count via aux cols |
| Insightful | Custom ranking queries, offsets analysis, term stats  |
