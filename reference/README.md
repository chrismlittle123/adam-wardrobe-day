# Reference photos

Source photos of Adam, used as reference images for outfit mock-ups.

- `adam.png` — the original snapshot (three-quarter angle, busy background).
- `adam-neutral.png` — generated clean base: facing camera, neutral expression,
  seamless white background. Use this one for outfit mock-ups; the plain
  background and head-on pose give the model far less to fight with.

Pass one to the image tool with `-i`:

```bash
uv run gemini-image "put him in a navy overshirt and cream trousers" \
  -i reference/adam-neutral.png -o out/adam-navy
```
