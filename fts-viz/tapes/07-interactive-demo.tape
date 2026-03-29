Output recordings/07-interactive-demo.gif

Set Shell bash
Set FontSize 14
Set Width 1000
Set Height 800
Set Theme "Catppuccin Mocha"
Set Padding 20

Type "./fts-viz"
Sleep 300ms
Enter
Sleep 1s

# Type search query
Type "tax capital gains"
Sleep 500ms
Enter
Sleep 2s

# Cycle through modes
Tab
Sleep 2s
Tab
Sleep 2s
Tab
Sleep 2s
Tab
Sleep 2s
Tab
Sleep 2s

# Back to mode 1 and try different query
Type@100ms "1"
Sleep 500ms

# Clear and type new query — use Ctrl+A, Ctrl+K to clear the input
Ctrl+A
Ctrl+K
Type "exchange rate EUR USD"
Sleep 500ms
Enter
Sleep 2s

# Show fancy mode
Type "4"
Sleep 2s

# Show insightful fancy
Type "6"
Sleep 3s

Escape
