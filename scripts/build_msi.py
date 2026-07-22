from __future__ import annotations

import argparse
from pathlib import Path
import sys
import uuid


APP_NAME = "BlogPilot"
MANUFACTURER = "BlogPilot"
UPGRADE_CODE = "{B59395E5-2D3E-4D46-A97E-D54E8CF1BC23}"
APPLICATION_COMPONENT = "{A79AB566-0980-4D5D-A417-075A6CE0118A}"
SHORTCUT_COMPONENT = "{789E14AC-E3EA-40C6-BBC0-24A7D0065E7C}"


def installer_payload(dist_dir: Path) -> list[Path]:
    executable = Path(dist_dir) / "BlogPilot.exe"
    if not executable.is_file():
        raise FileNotFoundError(executable)
    return [executable]


def _product_code(version: str) -> str:
    value = uuid.uuid5(uuid.UUID(UPGRADE_CODE.strip("{}")), version)
    return "{" + str(value).upper() + "}"


def _add_properties(db, msilib, version: str) -> None:
    msilib.add_data(
        db,
        "Property",
        [
            ("UpgradeCode", UPGRADE_CODE),
            ("ALLUSERS", "2"),
            ("MSIINSTALLPERUSER", "1"),
            ("ARPNOMODIFY", "1"),
            ("ARPNOREPAIR", "1"),
            ("ARPINSTALLLOCATION", "[INSTALLDIR]"),
            ("DefaultUIFont", "DlgFont8"),
            ("ErrorDialog", "ErrorDlg"),
            ("SecureCustomProperties", "OLDPRODUCTS"),
            ("LAUNCH_APP", "1"),
            ("ProductVersionDisplay", version),
        ],
    )


def _add_ui(db, msilib, executable_id: str) -> None:
    msilib.add_data(
        db,
        "TextStyle",
        [
            ("DlgFont8", "Segoe UI", 9, None, 0),
            ("DlgFontBold", "Segoe UI", 12, None, 1),
            ("DlgTitle", "Segoe UI", 17, None, 1),
        ],
    )
    visible = 3

    welcome = msilib.Dialog(
        db, "WelcomeDlg", 50, 50, 370, 270, visible, "[ProductName] 安装", "Install", "Install", "Cancel"
    )
    welcome.text("Title", 24, 22, 322, 30, visible, "{\\DlgTitle}安装 BlogPilot")
    welcome.text(
        "Description",
        24,
        66,
        322,
        78,
        visible,
        "程序将安装到当前用户目录。首次启动时，请选择专门的数据目录；升级和卸载不会删除文章、账号登录状态或运行记录。",
    )
    welcome.text("Location", 24, 150, 322, 28, visible, "程序目录：[INSTALLDIR]")
    welcome.line("BottomLine", 0, 224, 370, 0)
    install = welcome.pushbutton("Install", 228, 238, 64, 22, visible, "安装", "Cancel")
    install.event("EndDialog", "Return")
    cancel = welcome.pushbutton("Cancel", 298, 238, 64, 22, visible, "取消", "Install")
    cancel.event("EndDialog", "Exit")

    exit_dialog = msilib.Dialog(
        db, "ExitDialog", 50, 50, 370, 270, visible, "[ProductName] 安装", "Finish", "Finish", "Finish"
    )
    exit_dialog.text("Title", 24, 22, 322, 30, visible, "{\\DlgTitle}BlogPilot 已安装")
    exit_dialog.text(
        "Description",
        24,
        70,
        322,
        55,
        visible,
        "程序文件与用户数据彼此独立。首次启动将要求选择文章和账号数据的保存目录。",
    )
    exit_dialog.checkbox("Launch", 24, 148, 250, 20, visible, "LAUNCH_APP", "立即启动 BlogPilot", "Finish")
    exit_dialog.line("BottomLine", 0, 224, 370, 0)
    finish = exit_dialog.pushbutton("Finish", 290, 238, 72, 22, visible, "完成", "Finish")
    finish.event("DoAction", "LaunchApplication", "LAUNCH_APP = 1", 1)
    finish.event("EndDialog", "Return", "1", 2)

    for name, title, body in (
        ("FatalError", "安装失败", "BlogPilot 未能完成安装。请关闭占用程序文件的窗口后重试。"),
        ("UserExit", "安装已取消", "BlogPilot 没有安装，电脑上的现有数据未被更改。"),
    ):
        dialog = msilib.Dialog(db, name, 50, 50, 370, 190, visible, title, "Close", "Close", "Close")
        dialog.text("Title", 24, 22, 322, 28, visible, "{\\DlgFontBold}" + title)
        dialog.text("Body", 24, 62, 322, 55, visible, body)
        dialog.line("BottomLine", 0, 144, 370, 0)
        close = dialog.pushbutton("Close", 290, 156, 72, 22, visible, "关闭", "Close")
        close.event("EndDialog", "Return")

    error = msilib.Dialog(db, "ErrorDlg", 50, 50, 370, 190, visible, "安装提示", "Close", "Close", "Close")
    error.text("ErrorText", 24, 28, 322, 96, visible, "[ErrorText]")
    error.line("BottomLine", 0, 144, 370, 0)
    close = error.pushbutton("Close", 290, 156, 72, 22, visible, "确定", "Close")
    close.event("EndDialog", "ErrorReturn")

    msilib.add_data(db, "InstallUISequence", [("WelcomeDlg", "NOT Installed", 100)])
    msilib.add_data(db, "CustomAction", [("LaunchApplication", 18, executable_id, None)])


def build_msi(dist_dir: Path, version: str, output_path: Path) -> Path:
    try:
        import msilib
        from msilib import schema, sequence, text
    except ImportError as exc:
        raise RuntimeError("构建 MSI 需要项目当前使用的 Python 3.11（其中包含 msilib）") from exc

    dist_dir = Path(dist_dir).resolve()
    payload = installer_payload(dist_dir)
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    db = msilib.init_database(
        str(output_path),
        schema,
        APP_NAME,
        _product_code(version),
        version,
        MANUFACTURER,
    )
    msilib.add_tables(db, sequence)
    msilib.add_tables(db, text)
    _add_properties(db, msilib, version)
    msilib.add_data(
        db,
        "Upgrade",
        [(UPGRADE_CODE, None, version, None, 0, None, "OLDPRODUCTS")],
    )

    cab = msilib.CAB("blogpilot.cab")
    target = msilib.Directory(db, cab, None, str(dist_dir), "TARGETDIR", "SourceDir", 0)
    local = msilib.Directory(db, cab, target, "", "LocalAppDataFolder", ".", 0)
    programs = msilib.Directory(db, cab, local, "", "ProgramsFolder", "Programs", 0)
    install_dir = msilib.Directory(db, cab, programs, "", "INSTALLDIR", APP_NAME, 0)
    menu = msilib.Directory(db, cab, target, "", "ProgramMenuFolder", ".", 0)
    app_menu = msilib.Directory(db, cab, menu, "", "AppProgramMenuDir", APP_NAME, 0)
    msilib.Directory(db, cab, target, "", "DesktopFolder", ".", 0)

    feature = msilib.Feature(
        db,
        "MainFeature",
        APP_NAME,
        "BlogPilot desktop application",
        1,
        directory="INSTALLDIR",
    )
    feature.set_current()
    install_dir.start_component(
        "ApplicationFiles",
        feature,
        0,
        keyfile=payload[0].name,
        uuid=APPLICATION_COMPONENT,
    )
    executable_id = install_dir.add_file(payload[0].name)

    component_attributes = 4 | (256 if msilib.Win64 else 0)
    msilib.add_data(
        db,
        "Component",
        [("ApplicationShortcuts", SHORTCUT_COMPONENT, "INSTALLDIR", component_attributes, None, "InstalledRegistry")],
    )
    msilib.add_data(db, "FeatureComponents", [("MainFeature", "ApplicationShortcuts")])
    msilib.add_data(
        db,
        "Registry",
        [("InstalledRegistry", 1, r"Software\BlogPilot", "InstalledVersion", "[ProductVersion]", "ApplicationShortcuts")],
    )
    msilib.add_data(
        db,
        "Shortcut",
        [
            ("StartMenuShortcut", "AppProgramMenuDir", "BlogPilot", "ApplicationShortcuts", f"[#{executable_id}]", None, "BlogPilot 智博日更", None, None, None, None, "INSTALLDIR"),
            ("DesktopShortcut", "DesktopFolder", "BlogPilot", "ApplicationShortcuts", f"[#{executable_id}]", None, "BlogPilot 智博日更", None, None, None, None, "INSTALLDIR"),
        ],
    )
    msilib.add_data(
        db,
        "RemoveFile",
        [("RemoveStartMenuFolder", "ApplicationShortcuts", None, "AppProgramMenuDir", 2)],
    )
    _add_ui(db, msilib, executable_id)
    cab.commit(db)
    db.Commit()
    return output_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the BlogPilot Windows MSI installer")
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    output = args.output or args.dist / f"BlogPilot-Setup-{args.version}.msi"
    built = build_msi(args.dist, args.version, output)
    print(f"Built: {built}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
