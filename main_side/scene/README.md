# cobot3 scene bundle

`main_side/scene` contains large Isaac Sim scene assets and is not tracked in
GitHub.

Get the scene zip from the team Google Drive and extract it at the repository
root so the final layout is:

```text
cobot3/
  main_side/
    scene/
      gp_scene.usd
      assets/
      overrides/
      go2_unitree/
      go2_policy/
```

Expected local command:

```bash
cd /home/rokey/dev_ws/isaac_sim/cobot3
unzip /path/to/cobot3_scene.zip
```

Do not commit generated caches, backup USD files, `node_modules`, or `.next`.
