package main

import (
	"database/sql"
	"fmt"
	"math"
	"strings"

	_ "github.com/mattn/go-sqlite3"
)

// SearchResult holds a single FTS5 search result.
type SearchResult struct {
	DocID     int
	Title     string
	Category  string
	Body      string
	Rank      float64
	Snippet   string
	Highlight string
	MatchCount int
	BodyLen   int
}

// TermStat holds per-document term frequency info.
type TermStat struct {
	DocID    int
	Title    string
	Category string
	BodyLen  int
	Count    int
}

// DB wraps the SQLite FTS5 database.
type DB struct {
	conn *sql.DB
}

// NewDB creates an in-memory FTS5 database and seeds the corpus.
func NewDB() (*DB, error) {
	conn, err := sql.Open("sqlite3", ":memory:")
	if err != nil {
		return nil, err
	}

	// Create FTS5 virtual table
	_, err = conn.Exec(`
		CREATE VIRTUAL TABLE docs USING fts5(
			title,
			category,
			body,
			tokenize='porter ascii'
		);
	`)
	if err != nil {
		return nil, fmt.Errorf("create fts5 table: %w", err)
	}

	// Seed corpus
	for _, doc := range SampleCorpus {
		_, err = conn.Exec(
			`INSERT INTO docs(title, category, body) VALUES (?, ?, ?)`,
			doc.Title, doc.Category, doc.Body,
		)
		if err != nil {
			return nil, fmt.Errorf("insert doc %q: %w", doc.Title, err)
		}
	}

	return &DB{conn: conn}, nil
}

// Search performs an FTS5 query and returns ranked results.
func (db *DB) Search(query string) ([]SearchResult, error) {
	rows, err := db.conn.Query(`
		SELECT
			rowid,
			title,
			category,
			body,
			rank,
			snippet(docs, 2, '>>>', '<<<', '...', 32),
			highlight(docs, 2, '>>>', '<<<'),
			length(body)
		FROM docs
		WHERE docs MATCH ?
		ORDER BY rank
	`, query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var results []SearchResult
	for rows.Next() {
		var r SearchResult
		err := rows.Scan(&r.DocID, &r.Title, &r.Category, &r.Body, &r.Rank, &r.Snippet, &r.Highlight, &r.BodyLen)
		if err != nil {
			return nil, err
		}
		// Count matches by counting highlight markers
		r.MatchCount = strings.Count(r.Highlight, ">>>")
		results = append(results, r)
	}
	return results, rows.Err()
}

// TermStats returns per-document occurrence count for a specific term.
func (db *DB) TermStats(term string) ([]TermStat, error) {
	rows, err := db.conn.Query(`
		SELECT
			rowid,
			title,
			category,
			length(body)
		FROM docs
		WHERE docs MATCH ?
		ORDER BY rank
	`, term)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var stats []TermStat
	for rows.Next() {
		var s TermStat
		err := rows.Scan(&s.DocID, &s.Title, &s.Category, &s.BodyLen)
		if err != nil {
			return nil, err
		}
		// Count occurrences by querying highlight
		var highlighted string
		err = db.conn.QueryRow(
			`SELECT highlight(docs, 2, '>>>', '<<<') FROM docs WHERE rowid = ? AND docs MATCH ?`,
			s.DocID, term,
		).Scan(&highlighted)
		if err == nil {
			s.Count = strings.Count(highlighted, ">>>")
		}
		stats = append(stats, s)
	}
	return stats, rows.Err()
}

// AllDocTitles returns all document titles with their rowids.
func (db *DB) AllDocTitles() ([]struct{ ID int; Title string; Category string; BodyLen int }, error) {
	rows, err := db.conn.Query(`SELECT rowid, title, category, length(body) FROM docs`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var docs []struct{ ID int; Title string; Category string; BodyLen int }
	for rows.Next() {
		var d struct{ ID int; Title string; Category string; BodyLen int }
		if err := rows.Scan(&d.ID, &d.Title, &d.Category, &d.BodyLen); err != nil {
			return nil, err
		}
		docs = append(docs, d)
	}
	return docs, rows.Err()
}

// NormalizeScore converts a negative BM25 rank to a 0-1 score.
func NormalizeScore(rank float64, results []SearchResult) float64 {
	if len(results) == 0 {
		return 0
	}
	// BM25 ranks are negative; more negative = better match
	best := math.Abs(results[0].Rank)
	if best == 0 {
		return 0
	}
	return math.Abs(rank) / best
}

func (db *DB) Close() error {
	return db.conn.Close()
}
