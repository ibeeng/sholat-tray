import QtQuick
import Quickshell
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "Model.js" as Model

// Sholat Tray bar widget: next prayer + countdown in the bar, and the app's
// controls in a popup. The background app (sholat-tray) does the work: it
// writes today.json / state.json and takes commands on its command line.
BarWidget {
  id: root
  moduleName: "ibeeng.sholat-tray"
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  property bool popupOpen: false
  function close() { popupOpen = false }

  readonly property string cacheDir: Quickshell.env("HOME") + "/.cache/sholat-tray/"
  readonly property string binary: Quickshell.env("HOME") + "/.local/bin/sholat-tray"

  WatchedFile { id: cache; path: root.cacheDir + "today.json" }
  WatchedFile { id: stateFile; path: root.cacheDir + "state.json" }
  readonly property var sched: Model.parse(cache.text)
  readonly property var st: Model.parseState(stateFile.text)

  // Translated label for a style/color id; falls back to the app's own label.
  function itemLabel(prefix, item) {
    var key = prefix + "." + item.id
    var t = strings.t(key)
    return t && t !== key ? t : item.label
  }

  // args are fixed words or ids checked by Model.safeArg, never free text
  function send(args) {
    if (root.bar) root.bar.run("\"" + root.binary + "\" " + args)
  }

  property date now: new Date()
  Timer {
    // Countdown clock. Also retries the files until the app has written them
    // (a file that did not exist yet is not watched).
    interval: 15000; running: true; repeat: true; triggeredOnStart: true
    onTriggered: {
      if (!root.sched.ok) cache.reread()
      if (!root.st.ok) stateFile.reread()
      root.now = new Date()
    }
  }

  readonly property var nxt: sched.ok ? Model.next(sched.timings, now) : null
  readonly property bool soon: !!nxt && nxt.mins <= 10

  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    active: root.soon || root.st.playing
    // Name + time left only: the clock next to it already shows the time.
    text: root.st.playing ? "󰓛 Adzan"
      : root.nxt ? "󱠧 " + root.nxt.name + " · " + Model.countdown(root.nxt.mins)
      : "󱠧"
    tooltipText: !root.nxt ? strings.t("missing") : root.st.playing ? strings.t("playing") : ""
    onPressed: function(mouseButton) {
      if (mouseButton === Qt.RightButton && root.st.playing) root.send("stop-adzan")
      else if (mouseButton === Qt.LeftButton) root.popupOpen = !root.popupOpen
    }
  }

  component Label: Text {
    textFormat: Text.PlainText
    color: Commons.Color.popups.text
    font.family: Style.font.family
    font.pixelSize: Style.font.body
  }

  component Separator: Rectangle {
    width: parent ? parent.width : 0
    height: 1
    color: Commons.Color.popups.text
    opacity: 0.12
  }

  PopupCard {
    id: popup
    anchorItem: root
    bar: root.bar
    owner: root
    open: root.popupOpen && root.sched.ok
    contentWidth: popup.fittedContentWidth(Style.space(280))
    contentHeight: popup.fittedContentHeight(column.implicitHeight)

    Column {
      id: column
      width: parent.width
      spacing: Style.space(6)

      Label {
        width: parent.width
        elide: Text.ElideRight
        text: root.nxt ? strings.t("nextIn").arg(root.nxt.name).arg(Model.countdown(root.nxt.mins)) : strings.t("title")
        font.pixelSize: Style.font.subtitle
        font.bold: true
      }
      Label {
        width: parent.width
        elide: Text.ElideRight
        opacity: 0.6
        visible: text !== ""
        text: [root.st.city || root.sched.city, root.st.hijri].filter(function(s) { return !!s }).join(" · ")
      }

      Item { width: 1; height: Style.space(2) }

      Repeater {
        model: Model.ALL
        delegate: Item {
          required property string modelData
          readonly property bool isNext: !!root.nxt && root.nxt.name === modelData
          readonly property bool wajib: ["Subuh", "Dzuhur", "Ashar", "Maghrib", "Isya"].indexOf(modelData) >= 0
          width: column.width
          height: nameText.implicitHeight
          visible: !!root.sched.timings[modelData]

          Label {
            id: nameText
            anchors.left: parent.left
            text: (isNext ? "▸ " : "") + modelData
            color: isNext ? Commons.Color.accent : Commons.Color.popups.text
            opacity: wajib || isNext ? 1 : 0.55
            font.bold: isNext
          }
          Label {
            anchors.right: parent.right
            text: root.sched.timings[modelData] || ""
            color: isNext ? Commons.Color.accent : Commons.Color.popups.text
            opacity: wajib || isNext ? 1 : 0.55
            font.bold: isNext
          }
        }
      }

      Separator {}

      PopupMenuRow {
        text: strings.t("monthly")
        onTriggered: { root.send("monthly"); root.close() }
      }
      PopupMenuRow {
        text: strings.t("adzanAuto")
        checked: root.st.adzan
        onTriggered: root.send("adzan toggle")
      }
      PopupMenuRow {
        visible: root.st.playing
        text: strings.t("stopAdzan")
        onTriggered: root.send("stop-adzan")
      }
      PopupMenuRow {
        text: strings.t("testReminder")
        onTriggered: { root.send("test-overlay"); root.close() }
      }

      Separator { visible: root.st.styles.length > 0 }

      Label {
        visible: root.st.styles.length > 0
        text: strings.t("style")
        opacity: 0.6
        font.pixelSize: Style.font.caption || Style.font.body
      }
      Flow {
        width: parent.width
        spacing: Style.space(6)
        Repeater {
          model: root.st.styles
          delegate: Rectangle {
            required property var modelData
            readonly property bool selected: root.st.style === modelData.id
            width: chipText.implicitWidth + Style.space(20)
            height: chipText.implicitHeight + Style.space(10)
            radius: height / 2
            color: selected ? Commons.Color.accent : chipMouse.containsMouse ? Style.hoverFill : "transparent"
            border.width: 1
            border.color: selected ? Commons.Color.accent : Commons.Color.muted
            Label {
              id: chipText
              anchors.centerIn: parent
              text: root.itemLabel("style", modelData)
              color: selected ? Commons.Color.background : Commons.Color.popups.text
              font.bold: selected
            }
            MouseArea {
              id: chipMouse
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: {
                var id = Model.safeArg(modelData.id)
                if (id) root.send("style " + id)
              }
            }
          }
        }
      }

      Label {
        visible: root.st.colors.length > 0
        topPadding: Style.space(4)
        text: strings.t("color")
        opacity: 0.6
        font.pixelSize: Style.font.caption || Style.font.body
      }
      Row {
        visible: root.st.colors.length > 0
        spacing: Style.space(8)
        Repeater {
          model: root.st.colors
          delegate: Item {
            required property var modelData
            readonly property bool selected: root.st.color === modelData.id
            width: Style.space(26)
            height: width
            Rectangle {
              anchors.fill: parent
              radius: width / 2
              color: "transparent"
              border.width: 2
              border.color: Commons.Color.popups.text
              visible: parent.selected
            }
            Rectangle {
              anchors.centerIn: parent
              width: parent.width - Style.space(8)
              height: width
              radius: width / 2
              color: modelData.accent !== "" ? modelData.accent : Commons.Color.accent
            }
            MouseArea {
              anchors.fill: parent
              cursorShape: Qt.PointingHandCursor
              onClicked: {
                var id = Model.safeArg(modelData.id)
                if (id) root.send("color " + id)
              }
            }
          }
        }
      }
      Label {
        visible: text !== ""
        opacity: 0.7
        text: {
          for (var i = 0; i < root.st.colors.length; i++)
            if (root.st.colors[i].id === root.st.color) return root.itemLabel("color", root.st.colors[i])
          return ""
        }
      }
    }
  }
}
