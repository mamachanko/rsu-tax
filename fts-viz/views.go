package main

import (
	"fmt"
	"math"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

// ── Shared helpers ──────────────────────────────────────────────────────

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n-1] + "…"
}

func barGraph(pct float64, width int, ch string) string {
	filled := int(math.Round(pct * float64(width)))
	if filled > width {
		filled = width
	}
	return strings.Repeat(ch, filled) + strings.Repeat(" ", width-filled)
}

func wordCount(s string) int {
	return len(strings.Fields(s))
}

// ── View 1: Simple + Plain ──────────────────────────────────────────────

func viewSimplePlain(query string, results []SearchResult) string {
	var b strings.Builder

	b.WriteString(fmt.Sprintf("Search: %s\n", query))
	b.WriteString(fmt.Sprintf("Found %d results\n\n", len(results)))

	b.WriteString(fmt.Sprintf("  %-4s %-40s %-12s %s\n", "#", "Title", "Category", "Score"))
	b.WriteString(fmt.Sprintf("  %-4s %-40s %-12s %s\n", "---", strings.Repeat("-", 40), strings.Repeat("-", 12), "-------"))

	for i, r := range results {
		score := NormalizeScore(r.Rank, results)
		b.WriteString(fmt.Sprintf("  %-4d %-40s %-12s %.3f\n",
			i+1,
			truncate(r.Title, 40),
			r.Category,
			score,
		))
	}

	return b.String()
}

// ── View 2: Simple + Fancy ──────────────────────────────────────────────

func viewSimpleFancy(query string, results []SearchResult) string {
	headerStyle := lipgloss.NewStyle().
		Bold(true).
		Foreground(lipgloss.Color("12")).
		PaddingBottom(1)

	countStyle := lipgloss.NewStyle().
		Foreground(lipgloss.Color("8"))

	titleStyle := lipgloss.NewStyle().
		Bold(true).
		Foreground(lipgloss.Color("15"))

	catStyle := lipgloss.NewStyle().
		Foreground(lipgloss.Color("14"))

	barHigh := lipgloss.NewStyle().Foreground(lipgloss.Color("10"))
	barMid := lipgloss.NewStyle().Foreground(lipgloss.Color("11"))
	barLow := lipgloss.NewStyle().Foreground(lipgloss.Color("9"))

	var b strings.Builder

	b.WriteString(headerStyle.Render(fmt.Sprintf("  Search: %s", query)))
	b.WriteString("\n")
	b.WriteString(countStyle.Render(fmt.Sprintf("  %d documents matched", len(results))))
	b.WriteString("\n\n")

	for i, r := range results {
		score := NormalizeScore(r.Rank, results)

		// Choose bar color based on score
		barStyle := barLow
		if score > 0.7 {
			barStyle = barHigh
		} else if score > 0.4 {
			barStyle = barMid
		}

		bar := barStyle.Render(barGraph(score, 20, "█"))
		empty := lipgloss.NewStyle().Foreground(lipgloss.Color("236")).Render(barGraph(1-score, 0, " "))
		_ = empty

		line := fmt.Sprintf("  %s  %s  %s  %s %.0f%%",
			lipgloss.NewStyle().Foreground(lipgloss.Color("8")).Width(3).Align(lipgloss.Right).Render(fmt.Sprintf("%d.", i+1)),
			titleStyle.Width(38).Render(truncate(r.Title, 38)),
			catStyle.Width(10).Render(r.Category),
			bar,
			score*100,
		)
		b.WriteString(line)
		b.WriteString("\n")
	}

	return b.String()
}

// ── View 3: Moderate + Plain ────────────────────────────────────────────

func viewModeratePlain(query string, results []SearchResult) string {
	var b strings.Builder

	b.WriteString(fmt.Sprintf("Search: %s\n", query))
	b.WriteString(fmt.Sprintf("Found %d results\n", len(results)))
	b.WriteString(strings.Repeat("=", 72))
	b.WriteString("\n\n")

	for i, r := range results {
		score := NormalizeScore(r.Rank, results)

		b.WriteString(fmt.Sprintf("[%d] %s  (%s)  score=%.3f  matches=%d  words=%d\n",
			i+1, r.Title, r.Category, score, r.MatchCount, wordCount(r.Body)))

		// Format snippet: replace highlight markers with brackets
		snippet := r.Snippet
		snippet = strings.ReplaceAll(snippet, ">>>", "[")
		snippet = strings.ReplaceAll(snippet, "<<<", "]")

		lines := wrapText(snippet, 70)
		for _, line := range lines {
			b.WriteString(fmt.Sprintf("    %s\n", line))
		}
		b.WriteString("\n")
	}

	return b.String()
}

// ── View 4: Moderate + Fancy ────────────────────────────────────────────

func viewModerateFancy(query string, results []SearchResult) string {
	headerStyle := lipgloss.NewStyle().
		Bold(true).
		Foreground(lipgloss.Color("12"))

	titleStyle := lipgloss.NewStyle().
		Bold(true).
		Foreground(lipgloss.Color("15"))

	catBadge := lipgloss.NewStyle().
		Foreground(lipgloss.Color("0")).
		Background(lipgloss.Color("14")).
		Padding(0, 1)

	matchHL := lipgloss.NewStyle().
		Bold(true).
		Foreground(lipgloss.Color("11")).
		Background(lipgloss.Color("236"))

	dimStyle := lipgloss.NewStyle().
		Foreground(lipgloss.Color("8"))

	meterFull := lipgloss.NewStyle().Foreground(lipgloss.Color("10"))
	meterEmpty := lipgloss.NewStyle().Foreground(lipgloss.Color("236"))

	cardStyle := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(lipgloss.Color("237")).
		Padding(0, 1).
		Width(74)

	var b strings.Builder

	b.WriteString(headerStyle.Render(fmt.Sprintf("  Search: %s", query)))
	b.WriteString("  ")
	b.WriteString(dimStyle.Render(fmt.Sprintf("%d results", len(results))))
	b.WriteString("\n\n")

	for i, r := range results {
		score := NormalizeScore(r.Rank, results)
		meterWidth := 15
		filled := int(math.Round(score * float64(meterWidth)))
		meter := meterFull.Render(strings.Repeat("●", filled)) +
			meterEmpty.Render(strings.Repeat("○", meterWidth-filled))

		// Format snippet with highlights
		snippet := r.Snippet
		parts := strings.Split(snippet, ">>>")
		var formatted string
		for j, part := range parts {
			if j == 0 {
				formatted += part
				continue
			}
			idx := strings.Index(part, "<<<")
			if idx >= 0 {
				formatted += matchHL.Render(part[:idx]) + part[idx+3:]
			} else {
				formatted += part
			}
		}

		header := fmt.Sprintf("%s %s  %s",
			dimStyle.Render(fmt.Sprintf("#%d", i+1)),
			titleStyle.Render(r.Title),
			catBadge.Render(r.Category),
		)

		stats := fmt.Sprintf("%s  %s  %s",
			meter,
			dimStyle.Render(fmt.Sprintf("%d matches", r.MatchCount)),
			dimStyle.Render(fmt.Sprintf("%d words", wordCount(r.Body))),
		)

		wrapped := wrapText(formatted, 70)
		snippetBlock := strings.Join(wrapped, "\n")

		card := header + "\n" + stats + "\n" + snippetBlock
		b.WriteString(cardStyle.Render(card))
		b.WriteString("\n")
	}

	return b.String()
}

// ── View 5: Insightful + Plain ──────────────────────────────────────────

func viewInsightfulPlain(query string, results []SearchResult, db *DB) string {
	var b strings.Builder

	b.WriteString(fmt.Sprintf("Search: %s\n", query))
	b.WriteString(fmt.Sprintf("Results: %d / %d documents\n", len(results), len(SampleCorpus)))

	// Parse query into individual terms
	terms := parseQueryTerms(query)

	b.WriteString("\n--- Term Frequency per Document ---\n\n")

	// Header
	b.WriteString(fmt.Sprintf("  %-32s", "Document"))
	for _, t := range terms {
		b.WriteString(fmt.Sprintf(" %8s", truncate(t, 8)))
	}
	b.WriteString("    Total\n")
	b.WriteString("  " + strings.Repeat("-", 32))
	for range terms {
		b.WriteString(" " + strings.Repeat("-", 8))
	}
	b.WriteString("  -------\n")

	// Per-document stats
	for _, r := range results {
		b.WriteString(fmt.Sprintf("  %-32s", truncate(r.Title, 32)))
		total := 0
		for _, t := range terms {
			count := countTermInHighlight(db, r.DocID, t)
			total += count
			b.WriteString(fmt.Sprintf(" %8d", count))
		}
		b.WriteString(fmt.Sprintf("  %7d", total))
		b.WriteString("\n")
	}

	// Corpus coverage
	b.WriteString("\n--- Corpus Coverage ---\n\n")
	b.WriteString(fmt.Sprintf("  %-20s  Docs  Coverage\n", "Term"))
	b.WriteString("  " + strings.Repeat("-", 20) + "  ----  --------\n")

	for _, t := range terms {
		stats, _ := db.TermStats(t)
		pct := float64(len(stats)) / float64(len(SampleCorpus)) * 100
		b.WriteString(fmt.Sprintf("  %-20s  %4d  %5.1f%%\n", t, len(stats), pct))
	}

	// Score distribution
	b.WriteString("\n--- Score Distribution ---\n\n")
	for _, r := range results {
		score := NormalizeScore(r.Rank, results)
		bar := barGraph(score, 30, "#")
		b.WriteString(fmt.Sprintf("  %-28s |%s| %.1f%%\n",
			truncate(r.Title, 28), bar, score*100))
	}

	return b.String()
}

// ── View 6: Insightful + Fancy ──────────────────────────────────────────

func viewInsightfulFancy(query string, results []SearchResult, db *DB) string {
	headerStyle := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("12"))
	dimStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("8"))
	termStyle := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("13"))
	titleStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("15"))
	sectionStyle := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("14")).PaddingTop(1)

	terms := parseQueryTerms(query)

	var b strings.Builder

	b.WriteString(headerStyle.Render(fmt.Sprintf("  Search: %s", query)))
	b.WriteString("  ")
	b.WriteString(dimStyle.Render(fmt.Sprintf("%d/%d docs matched", len(results), len(SampleCorpus))))
	b.WriteString("\n")

	// ── Coverage heat map ──
	b.WriteString(sectionStyle.Render("  Coverage Heat Map"))
	b.WriteString("\n\n")

	// Header row with term names
	b.WriteString(fmt.Sprintf("  %-30s ", ""))
	for _, t := range terms {
		b.WriteString(termStyle.Render(fmt.Sprintf(" %-8s", truncate(t, 8))))
	}
	b.WriteString("\n")

	// Heat map rows
	heatColors := []string{"16", "52", "88", "124", "160", "196", "202", "208", "214", "220"}
	for _, r := range results {
		b.WriteString(fmt.Sprintf("  %s ", titleStyle.Width(30).Render(truncate(r.Title, 30))))
		for _, t := range terms {
			count := countTermInHighlight(db, r.DocID, t)
			// Map count to heat color
			idx := count
			if idx >= len(heatColors) {
				idx = len(heatColors) - 1
			}
			cell := " ░░ "
			if count == 0 {
				cell = lipgloss.NewStyle().Foreground(lipgloss.Color("236")).Render("  ·  ")
			} else {
				cellStyle := lipgloss.NewStyle().
					Background(lipgloss.Color(heatColors[idx])).
					Foreground(lipgloss.Color("15")).
					Bold(true)
				cell = cellStyle.Render(fmt.Sprintf(" %2d  ", count))
			}
			b.WriteString(cell)
			b.WriteString("  ")
		}
		b.WriteString("\n")
	}

	// ── Relevance sparklines ──
	b.WriteString(sectionStyle.Render("  Relevance Sparklines"))
	b.WriteString("\n\n")

	sparkChars := []string{"▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"}
	for _, r := range results {
		score := NormalizeScore(r.Rank, results)
		sparkWidth := 20
		filled := int(math.Round(score * float64(sparkWidth)))

		var spark string
		for i := 0; i < sparkWidth; i++ {
			if i < filled {
				// Gradient effect: bars get taller toward the score
				level := int(float64(i) / float64(filled) * float64(len(sparkChars)-1))
				color := "10" // green
				if score < 0.4 {
					color = "9" // red
				} else if score < 0.7 {
					color = "11" // yellow
				}
				spark += lipgloss.NewStyle().Foreground(lipgloss.Color(color)).Render(sparkChars[level])
			} else {
				spark += dimStyle.Render("▁")
			}
		}

		pct := lipgloss.NewStyle().Foreground(lipgloss.Color("15")).Width(5).Align(lipgloss.Right).Render(fmt.Sprintf("%.0f%%", score*100))
		b.WriteString(fmt.Sprintf("  %s  %s %s\n",
			titleStyle.Width(30).Render(truncate(r.Title, 30)),
			spark,
			pct,
		))
	}

	// ── Term importance ──
	b.WriteString(sectionStyle.Render("  Term Selectivity"))
	b.WriteString("\n\n")

	for _, t := range terms {
		stats, _ := db.TermStats(t)
		coverage := float64(len(stats)) / float64(len(SampleCorpus))
		selectivity := 1 - coverage // rarer = more selective

		selBar := barGraph(selectivity, 20, "█")
		covBar := barGraph(coverage, 20, "░")

		selColor := "10"
		if selectivity < 0.3 {
			selColor = "9"
		} else if selectivity < 0.6 {
			selColor = "11"
		}

		b.WriteString(fmt.Sprintf("  %s  sel %s  cov %s  %s\n",
			termStyle.Width(12).Render(t),
			lipgloss.NewStyle().Foreground(lipgloss.Color(selColor)).Render(selBar),
			dimStyle.Render(covBar),
			dimStyle.Render(fmt.Sprintf("%d/%d docs", len(stats), len(SampleCorpus))),
		))
	}

	// ── Match density ──
	b.WriteString(sectionStyle.Render("  Match Density (matches per 100 words)"))
	b.WriteString("\n\n")

	for _, r := range results {
		wc := wordCount(r.Body)
		density := float64(r.MatchCount) / float64(wc) * 100
		maxDensity := 15.0
		pct := density / maxDensity
		if pct > 1 {
			pct = 1
		}
		dBar := barGraph(pct, 25, "▓")

		color := "10"
		if density > 8 {
			color = "9"
		} else if density > 4 {
			color = "11"
		}

		b.WriteString(fmt.Sprintf("  %s  %s  %s\n",
			titleStyle.Width(30).Render(truncate(r.Title, 30)),
			lipgloss.NewStyle().Foreground(lipgloss.Color(color)).Render(dBar),
			dimStyle.Render(fmt.Sprintf("%.1f/100w", density)),
		))
	}

	return b.String()
}

// ── Helpers ─────────────────────────────────────────────────────────────

func parseQueryTerms(query string) []string {
	// Split on spaces, ignore boolean operators
	words := strings.Fields(query)
	var terms []string
	for _, w := range words {
		w = strings.ToLower(w)
		if w == "and" || w == "or" || w == "not" || w == "near" {
			continue
		}
		w = strings.Trim(w, `"()`)
		if w != "" {
			terms = append(terms, w)
		}
	}
	return terms
}

func countTermInHighlight(db *DB, docID int, term string) int {
	var highlighted string
	err := db.conn.QueryRow(
		`SELECT highlight(docs, 2, '>>>', '<<<') FROM docs WHERE rowid = ? AND docs MATCH ?`,
		docID, term,
	).Scan(&highlighted)
	if err != nil {
		return 0
	}
	return strings.Count(highlighted, ">>>")
}

func wrapText(s string, width int) []string {
	words := strings.Fields(s)
	if len(words) == 0 {
		return nil
	}
	var lines []string
	current := words[0]
	for _, w := range words[1:] {
		if len(current)+1+len(w) > width {
			lines = append(lines, current)
			current = w
		} else {
			current += " " + w
		}
	}
	if current != "" {
		lines = append(lines, current)
	}
	return lines
}
