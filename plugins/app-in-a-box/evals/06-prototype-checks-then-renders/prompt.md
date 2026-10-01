---
max_turns: 20
timeout_seconds: 420
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
runs: 3
---
I'm at the prototype step of App in a Box (the kit root is wherever this plugin lives).
Save this as `design/prototype.json`, make it pass the kit's prototype checks, then render
it to `design/prototype.html`. Don't ask me anything.

```json
{"version":1,"app":{"name":"Sample List","tagline":"A shared grocery list for housemates."},"directions":[{"id":"calm","label":"Calm","why":"Quiet neutrals, one accent.","icons":"rounded","tokens":{"name":"calm","version":2,"mode":"light","color":{"light":{"bg":"#F6F7F4","surface":"#FFFFFF","surfaceRaised":"#FFFFFF","control":"#EEF1EC","border":"#D9DED6","ink":"#17201B","inkDim":"#46514A","inkFaint":"#5A645D","accent":"#2F6B4F","onAccent":"#FFFFFF","success":"#1B7F55","warning":"#955800","danger":"#BE2E45","shadow":"#1C2A22"},"dark":{"bg":"#0F1411","surface":"#171D19","surfaceRaised":"#1E2621","control":"#171D19","border":"#2C3630","ink":"#E8EEE9","inkDim":"#B3BEB6","inkFaint":"#97A39A","accent":"#6FCB9F","onAccent":"#0F1411","success":"#5BD69C","warning":"#F2B24C","danger":"#FF7A85","shadow":"#000000"}}}}],"defaults":{"direction":"calm","mode":"light","density":"regular","temperature":"calm","tone":"calm"},"features":[],"tabs":[{"screen":"list","label":"List","icon":"list"}],"screens":[{"id":"list","title":"List","variants":[{"id":"default","label":"Default","blocks":[{"type":"header","title":"This week","subtitle":"Lorem ipsum dolor sit amet"},{"type":"list","items":[{"title":"Oat milk","meta":"Added by Sam"},{"title":"Eggs","meta":"Added by Jo"}]},{"type":"button","label":"Add item","style":"primary","icon":"plus","action":{"toast":"Added"}}]}],"states":{"empty":[{"type":"empty","icon":"list","title":"Nothing on the list","body":"Add the first thing you're out of."}]}}]}
```
