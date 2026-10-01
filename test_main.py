import os, tempfile, main
main.STARS = os.path.join(tempfile.mkdtemp(), "s.json")
main.vscode_projects = lambda: [dict(key="vscode|a", ide="vscode", name="a", path="/a", where="", cmd=["x"]),
                                dict(key="vscode|b", ide="vscode", name="b", path="/b", where="WSL", cmd=["x"])]
main.zed_projects = lambda: [dict(key="zed|c", ide="zed", name="c", path="/c", where="", cmd=["z"])]
assert [r["Title"] for r in main.query("")] == ["a", "c", "b"]
main.toggle_star("vscode|b"); main.toggle_star("zed|c")
assert [r["Title"] for r in main.query("")] == ["★ b", "★ c", "a"]  # starred alphabetical first
main.toggle_star("vscode|b"); main.toggle_star("zed|c")
main.toggle_star("zed|c")
r = main.query("")
assert r[0]["Title"] == "★ c" and main.context_menu(r[0]["ContextData"])[0]["Title"] == "Unstar"
assert [x["Title"] for x in main.query("wsl")] == ["b"]
main.toggle_star("zed|c"); assert not main.load_stars()
print("ok")
