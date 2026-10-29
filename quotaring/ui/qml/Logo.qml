import QtQuick

// The QuotaRing mark — a Q drawn as a gauge: a 270° ring and a tail — in one colour.
// Same geometry as the app icon (app.make_icon, docs/brand/build_logo.py), on a 256 canvas;
// the heavier cut, as at small sizes, so the ring stays open and the tail visible.
Canvas {
    id: logo
    property color color
    implicitWidth: 22
    implicitHeight: 22
    onColorChanged: requestPaint()
    onPaint: {
        const ctx = getContext("2d");
        ctx.reset();
        const k = width / 256, c = 128, r = 86, w = 52, tail = 120, d = Math.SQRT1_2;
        ctx.strokeStyle = logo.color;
        ctx.lineWidth = w * k;
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.arc(c * k, c * k, r * k, -Math.PI / 2, Math.PI, false);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo((c + r * d) * k, (c + r * d) * k);
        ctx.lineTo((c + tail * d) * k, (c + tail * d) * k);
        ctx.stroke();
    }
}
