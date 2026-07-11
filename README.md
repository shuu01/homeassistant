# Voice assistant architecture

Microphone
     │
     ▼
 Wake Word
     │
     ▼
 Recording
     │
     ▼
     AI ───────────────┐
     │                 │
     ▼                 ▼
 Memory           Conversation
     │                 │
     └────────┬────────┘
              ▼
             TTS
              │
              ▼
           Speaker
