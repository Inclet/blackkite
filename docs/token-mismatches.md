# Token vs reference mismatches

The reference wins in every case (brief rule).

| Where | Token says | Reference does |
|---|---|---|
| icons.json `_usage` | All icons round caps and joins | Dashed "unconfirmed" trust circle has neither |
| Buttons, chips, inputs | `--bk-font: 'Figtree', system-ui, sans-serif` | `'Figtree', sans-serif` (renders the same while Figtree loads) |
| --bk-orbit | 8s; 6s in loading | Foundations signature uses 14s (decision 9) |
| Motion tokens | Three durations, one easing | Foundations glide 7s ease-in-out, drop 5s ease-out loop (decision 9) |
| Space scale | 4–48 steps | Boards use 9, 18, 22, 36, 40, 44, 56 px gaps and paddings |
| Line heights | Token lines only | 1.45 and 1.5 used for notes |
| Trust panel | — | `#F6F5F2` on desktop pane, `#EFEDE9` on phone |
| Digest email | 600 max weight, 14px card radius | `bold` (700), 12px radius (decision 8) |
