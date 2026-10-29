.pragma library
// Shared helpers for the popup.

function pct(view, n) {
    return view && view.language === "tr" ? "%" + n : n + "%";
}

// Level of a limit from what is left: the colour language of the widget.
function levelOf(remaining, limited) {
    if (limited || remaining <= 10) return "bad";
    if (remaining <= 30) return "warn";
    return "ok";
}
