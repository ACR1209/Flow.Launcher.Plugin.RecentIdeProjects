"""Flow Launcher plugin: recent VS Code + Zed projects, with stars. Stdlib only."""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlparse

HOME = os.environ.get("USERPROFILE") or os.path.expanduser("~")
LOCAL = os.environ.get("LOCALAPPDATA") or os.path.join(HOME, "AppData", "Local")
STARS = os.path.join(os.environ.get("APPDATA") or HOME, "FlowLauncher", "Settings", "Plugins",
                     "RecentIdeProjects.stars.json")
VSCODE_DBS = [  # (tag, exe, db) -- new shared location first, then legacy
    ("Code", os.path.join(LOCAL, "Programs", "Microsoft VS Code", "Code.exe"),
     [os.path.join(HOME, ".vscode-shared", "sharedStorage", "state.vscdb"),
      os.path.join(os.environ.get("APPDATA", ""), "Code", "User", "globalStorage", "state.vscdb")]),
]
ZED_EXE = os.path.join(LOCAL, "Programs", "Zed", "bin", "Zed.exe")  # CLI; hands off to the running Zed
ZED_DB_GLOB = os.path.join(LOCAL, "Zed", "db")
ICON = {"vscode": "Images/vsCode.png", "zed": "Images/zed.png"}


def read_kv(db, sql, args=()):
    """Query a possibly-locked sqlite db via a temp copy (incl. WAL)."""
    if not os.path.exists(db):
        return []
    tmp = tempfile.mkdtemp()
    try:
        for suf in ("", "-wal", "-shm"):
            if os.path.exists(db + suf):
                shutil.copy(db + suf, os.path.join(tmp, "d.sqlite" + suf))
        con = sqlite3.connect(os.path.join(tmp, "d.sqlite"))
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def vscode_projects():
    out, seen = [], set()
    for tag, exe, dbs in VSCODE_DBS:
        for db in dbs:
            rows = read_kv(db, "select value from ItemTable where key='history.recentlyOpenedPathsList'")
            for (val,) in rows:
                for e in json.loads(val).get("entries", []):
                    uri, kind = e.get("folderUri"), "--folder-uri"
                    if not uri and e.get("workspace"):
                        uri, kind = e["workspace"].get("configPath"), "--file-uri"
                    if not uri or uri in seen:
                        continue
                    seen.add(uri)
                    u = urlparse(uri)
                    path = unquote(u.path)
                    if u.scheme == "file":
                        path = path.lstrip("/") if u.netloc == "" else "//%s%s" % (u.netloc, path)
                        where = "WSL" if u.netloc.startswith("wsl") else ""
                    else:
                        where = unquote(e.get("remoteAuthority") or u.netloc)
                    name = os.path.basename(path.rstrip("/\\")) or path
                    out.append(dict(key="vscode|" + uri, ide="vscode", name=name, path=path, where=where,
                                    cmd=[exe, kind, uri]))
    return out


def zed_projects():
    out = []
    dbs = []
    if os.path.isdir(ZED_DB_GLOB):
        dbs = [os.path.join(ZED_DB_GLOB, d, "db.sqlite") for d in os.listdir(ZED_DB_GLOB)]
    for db in dbs:
        rows = read_kv(db, """select w.paths, r.kind, r.host, r.port, r.user, r.distro
            from workspaces w left join remote_connections r on r.id = w.remote_connection_id
            where w.paths != '' order by w.timestamp desc""")
        for paths, kind, host, port, user, distro in rows:
            path = paths.split("\n")[0]
            if kind == "wsl":
                cmd, where = [ZED_EXE, "--wsl", (user + "@" if user else "") + distro, path], "WSL: " + distro
            elif kind == "ssh":
                cmd = [ZED_EXE, "ssh://%s%s%s%s" % (user + "@" if user else "", host, ":%s" % port if port else "", path)]
                where = "SSH: " + host
            elif kind:
                continue  # ponytail: docker/other Zed remotes unsupported, add when needed
            else:
                cmd, where = [ZED_EXE, path], ""
            if any(o["cmd"] == cmd for o in out):
                continue  # same project can appear in several Zed workspace rows
            out.append(dict(key="zed|" + " ".join(cmd[1:]), ide="zed", name=os.path.basename(path.rstrip("/\\")) or path,
                            path=path, where=where, cmd=cmd))
    return out


def load_stars():
    try:
        with open(STARS, encoding="utf-8") as f:
            return set(json.load(f))
    except (OSError, ValueError):
        return set()


def toggle_star(key):
    s = load_stars()
    s ^= {key}
    now = key in s
    os.makedirs(os.path.dirname(STARS), exist_ok=True)
    with open(STARS, "w", encoding="utf-8") as f:
        json.dump(sorted(s), f)
    return now


def merged():
    """Starred first (alphabetical); the rest interleaved by per-IDE recency rank (VS Code has no timestamps)."""
    stars = load_stars()
    lists = [vscode_projects(), zed_projects()]
    items = [p for _, p in sorted(((i, p) for L in lists for i, p in enumerate(L)), key=lambda t: t[0])]
    for p in items:
        p["starred"] = p["key"] in stars
    starred = sorted((p for p in items if p["starred"]), key=lambda p: (p["name"].lower(), p["ide"]))
    return starred + [p for p in items if not p["starred"]]


def query(q):
    raw = [q]
    q = q.lower().split()
    res = []
    for rank, p in enumerate(merged()):
        hay = (p["name"] + " " + p["path"] + " " + p["where"] + " " + p["ide"]).lower()
        if all(t in hay for t in q):
            tag = "VS Code" if p["ide"] == "vscode" else "Zed"
            res.append({
                "Title": ("★ " if p["starred"] else "") + p["name"],
                "SubTitle": "%s%s — %s" % (tag, " [%s]" % p["where"] if p["where"] else "", p["path"]),
                "IcoPath": ICON[p["ide"]],
                "Score": 10_000_000 - rank,  # Flow sorts by Score (plus a per-title "times opened" boost, disabled below)
                "AddSelectedCount": False,
                "ContextData": [p["key"], p["starred"], raw[0]],
                "JsonRPCAction": {"method": "open", "parameters": [p["cmd"]]},
            })
    return res


def context_menu(data):
    key, starred, q = data
    return [{
        "Title": "Unstar" if starred else "Star",
        "SubTitle": key.split("|", 1)[1],
        "IcoPath": ICON[key.split("|")[0]],
        "JsonRPCAction": {"method": "star", "parameters": [key, q], "dontHideAfterAction": True},
    }]


def main():
    req = json.loads(sys.argv[1])
    m, a = req["method"], req.get("parameters", [])
    if m == "query":
        print(json.dumps({"result": query(a[0] if a else "")}))
    elif m == "context_menu":
        print(json.dumps({"result": context_menu(a[0])}))
    elif m == "star":
        toggle_star(a[0])
        print(json.dumps({"method": "Flow.Launcher.ReQuery", "parameters": [True]}))
    elif m == "open":
        flags = 0x08000000 | 0x00000200 if os.name == "nt" else 0  # NO_WINDOW | NEW_GROUP
        subprocess.Popen(a[0], creationflags=flags, close_fds=True)
        print("{}")


if __name__ == "__main__":
    main()
