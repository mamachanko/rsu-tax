package main

import (
	"fmt"
	"os"
	"strings"

	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

type viewMode int

const (
	modeSimplePlain viewMode = iota
	modeSimpleFancy
	modeModeratePlain
	modeModerateFancy
	modeInsightfulPlain
	modeInsightfulFancy
)

var modeNames = map[viewMode]string{
	modeSimplePlain:     "Simple + Plain",
	modeSimpleFancy:     "Simple + Fancy",
	modeModeratePlain:   "Moderate + Plain",
	modeModerateFancy:   "Moderate + Fancy",
	modeInsightfulPlain: "Insightful + Plain",
	modeInsightfulFancy: "Insightful + Fancy",
}

type model struct {
	db        *DB
	input     textinput.Model
	query     string
	results   []SearchResult
	mode      viewMode
	err       error
	width     int
	height    int
	scroll    int
	searching bool
}

func initialModel(db *DB) model {
	ti := textinput.New()
	ti.Placeholder = "enter search query (e.g. tax capital gains)"
	ti.Focus()
	ti.Width = 50

	return model{
		db:    db,
		input: ti,
		mode:  modeSimplePlain,
	}
}

type searchDoneMsg struct {
	results []SearchResult
	err     error
}

func (m model) Init() tea.Cmd {
	return textinput.Blink
}

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c", "esc":
			return m, tea.Quit
		case "enter":
			if m.input.Value() != "" {
				m.query = m.input.Value()
				m.searching = true
				m.scroll = 0
				results, err := m.db.Search(m.query)
				m.results = results
				m.err = err
				m.searching = false
			}
			return m, nil
		case "tab":
			m.mode = (m.mode + 1) % 6
			return m, nil
		case "shift+tab":
			m.mode = (m.mode + 5) % 6
			return m, nil
		case "up", "k":
			if m.scroll > 0 {
				m.scroll--
			}
			return m, nil
		case "down", "j":
			m.scroll++
			return m, nil
		case "1":
			m.mode = modeSimplePlain
			return m, nil
		case "2":
			m.mode = modeSimpleFancy
			return m, nil
		case "3":
			m.mode = modeModeratePlain
			return m, nil
		case "4":
			m.mode = modeModerateFancy
			return m, nil
		case "5":
			m.mode = modeInsightfulPlain
			return m, nil
		case "6":
			m.mode = modeInsightfulFancy
			return m, nil
		}
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		return m, nil
	}

	var cmd tea.Cmd
	m.input, cmd = m.input.Update(msg)
	return m, cmd
}

func (m model) View() string {
	var b strings.Builder

	// Title bar
	titleBar := lipgloss.NewStyle().
		Bold(true).
		Foreground(lipgloss.Color("15")).
		Background(lipgloss.Color("62")).
		Padding(0, 1).
		Width(78).
		Render("FTS5 Visualization Explorer")

	b.WriteString(titleBar)
	b.WriteString("\n\n")

	// Search input
	b.WriteString("  ")
	b.WriteString(m.input.View())
	b.WriteString("\n\n")

	// Mode tabs
	for i := viewMode(0); i < 6; i++ {
		style := lipgloss.NewStyle().Padding(0, 1)
		if i == m.mode {
			style = style.Bold(true).
				Foreground(lipgloss.Color("15")).
				Background(lipgloss.Color("62"))
		} else {
			style = style.Foreground(lipgloss.Color("8"))
		}
		b.WriteString(style.Render(fmt.Sprintf("%d:%s", i+1, modeNames[i])))
		if i < 5 {
			b.WriteString(" ")
		}
	}
	b.WriteString("\n\n")

	// Results area
	if m.err != nil {
		errStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("9"))
		b.WriteString(errStyle.Render(fmt.Sprintf("  Error: %v", m.err)))
	} else if m.query == "" {
		helpStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("8"))
		b.WriteString(helpStyle.Render("  Type a query and press Enter to search."))
		b.WriteString("\n")
		b.WriteString(helpStyle.Render("  Press 1-6 or Tab to switch visualization modes."))
		b.WriteString("\n")
		b.WriteString(helpStyle.Render("  Press j/k or arrow keys to scroll. Esc to quit."))
		b.WriteString("\n\n")
		b.WriteString(helpStyle.Render("  Sample queries:"))
		b.WriteString("\n")
		b.WriteString(helpStyle.Render("    tax capital gains"))
		b.WriteString("\n")
		b.WriteString(helpStyle.Render("    exchange rate EUR USD"))
		b.WriteString("\n")
		b.WriteString(helpStyle.Render("    RSU vesting sell"))
		b.WriteString("\n")
		b.WriteString(helpStyle.Render("    CSV parsing data"))
		b.WriteString("\n")
		b.WriteString(helpStyle.Render("    terminal interface"))
	} else if len(m.results) == 0 {
		b.WriteString(lipgloss.NewStyle().Foreground(lipgloss.Color("11")).Render("  No results found."))
	} else {
		var content string
		switch m.mode {
		case modeSimplePlain:
			content = viewSimplePlain(m.query, m.results)
		case modeSimpleFancy:
			content = viewSimpleFancy(m.query, m.results)
		case modeModeratePlain:
			content = viewModeratePlain(m.query, m.results)
		case modeModerateFancy:
			content = viewModerateFancy(m.query, m.results)
		case modeInsightfulPlain:
			content = viewInsightfulPlain(m.query, m.results, m.db)
		case modeInsightfulFancy:
			content = viewInsightfulFancy(m.query, m.results, m.db)
		}

		// Apply scroll
		lines := strings.Split(content, "\n")
		if m.scroll >= len(lines) {
			m.scroll = len(lines) - 1
		}
		if m.scroll < 0 {
			m.scroll = 0
		}
		maxLines := 35
		if m.height > 10 {
			maxLines = m.height - 10
		}
		end := m.scroll + maxLines
		if end > len(lines) {
			end = len(lines)
		}
		visible := lines[m.scroll:end]
		b.WriteString(strings.Join(visible, "\n"))
	}

	// Footer
	b.WriteString("\n\n")
	footerStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("8"))
	b.WriteString(footerStyle.Render("  Tab: next mode | 1-6: jump to mode | j/k: scroll | Esc: quit"))

	return b.String()
}

func main() {
	// Allow passing a mode and query via args for VHS recording
	db, err := NewDB()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to create database: %v\n", err)
		os.Exit(1)
	}
	defer db.Close()

	// Non-interactive mode for VHS: fts-viz --static <mode> <query>
	if len(os.Args) >= 4 && os.Args[1] == "--static" {
		mode := os.Args[2]
		query := strings.Join(os.Args[3:], " ")
		results, err := db.Search(query)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Search error: %v\n", err)
			os.Exit(1)
		}

		switch mode {
		case "1":
			fmt.Print(viewSimplePlain(query, results))
		case "2":
			fmt.Print(viewSimpleFancy(query, results))
		case "3":
			fmt.Print(viewModeratePlain(query, results))
		case "4":
			fmt.Print(viewModerateFancy(query, results))
		case "5":
			fmt.Print(viewInsightfulPlain(query, results, db))
		case "6":
			fmt.Print(viewInsightfulFancy(query, results, db))
		default:
			fmt.Fprintf(os.Stderr, "Unknown mode: %s (use 1-6)\n", mode)
			os.Exit(1)
		}
		return
	}

	p := tea.NewProgram(initialModel(db), tea.WithAltScreen())
	if _, err := p.Run(); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}
