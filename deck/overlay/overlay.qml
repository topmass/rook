// Rook's overlay window for a Qt WebEngine host (qmlscene on Qt 5, qml on Qt 6). rook_overlay.py fills the @...@
// fields, starts the host, then tags the X window GAMESCOPE_EXTERNAL_OVERLAY and gives it an empty input shape.
// The window maps only while the page shows something (window.rookOverlay.visible()), so gamescope composites
// nothing over the game the rest of the time.
@IMPORTS@

Window {
    id: win
    title: "Rook Overlay"
    x: @X@
    y: @Y@
    width: @W@
    height: @H@
    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput
           | Qt.WindowDoesNotAcceptFocus | Qt.X11BypassWindowManagerHint
    visible: true

    WebEngineView {
        id: view
        anchors.fill: parent
        backgroundColor: "transparent"
        url: "@URL@"
    }

    // The page loads before the backend serves it at boot: try again until it has its title.
    Timer {
        interval: 3000
        running: true
        repeat: true
        onTriggered: if (!view.loading && view.title !== "Rook Overlay") view.reload()
    }

    // Map the window only while the page shows something.
    Timer {
        interval: 400
        running: true
        repeat: true
        onTriggered: view.runJavaScript("!!(window.rookOverlay && window.rookOverlay.visible())",
                                        function (shown) { win.visible = (shown === true) || @ALWAYS@; })
    }
}
