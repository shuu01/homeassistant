## Voice assistant architecture

```text
+------------+
| Microphone |
+------------+
      |
      v
+------------+
| Wake Word  |
+------------+
      |
      v
+------------+
| Recording  |
+------------+
      |
      v
+------------+
|     AI     |
+------------+
      |
  +---+---+
  |       |
  v       v
Memory  Conversation
  |       |
  +---+---+
      |
      v
+------------+
|    TTS     |
+------------+
      |
      v
+------------+
|  Speaker   |
+------------+
```
