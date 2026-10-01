import os, tempfile, main
d = tempfile.mkdtemp()
main.STARS, main.HIDDEN = os.path.join(d, "s.json"), os.path.join(d, "h.json")
main.vscode_projects = lambda: [dict(key="vscode|a", ide="vscode", name="a", path="/a", where="", cmd=["x"]),
                                dict(key="vscode|b", ide="vscode", name="b", path="/b", where="WSL", cmd=["x"])]
main.zed_projects = lambda: [dict(key="zed|c", ide="zed", name="c", path="/c", where="", cmd=["z"])]
titles = lambda q="": [r["Title"] for r in main.query(q)]
assert titles() == ["a", "c", "b"]
main.toggle(main.STARS, "vscode|b"); main.toggle(main.STARS, "zed|c")
assert titles() == ["★ b", "★ c", "a"]  # starred alphabetical first
scores = [r["Score"] for r in main.query("")]
assert scores == sorted(scores, reverse=True)
r = main.query("")
assert main.context_menu(r[0]["ContextData"])[0]["Title"] == "Unstar"
assert titles("wsl") == ["★ b"]
main.toggle(main.STARS, "vscode|b"); main.toggle(main.STARS, "zed|c")
assert not main.load(main.STARS)
# hide / hidden view / unhide
main.toggle(main.HIDDEN, "vscode|a")
assert titles() == ["c", "b"] and titles("hidden") == ["a"] and titles("hidden zzz") == []
assert main.context_menu(main.query("hidden")[0]["ContextData"])[1]["Title"] == "Unhide"
main.toggle(main.HIDDEN, "vscode|a")
assert titles() == ["a", "c", "b"] and titles("hidden") == []
print("ok")
