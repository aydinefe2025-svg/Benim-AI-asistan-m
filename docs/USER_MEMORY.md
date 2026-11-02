# User-controlled memory library

The assistant can use a small set of notes that the user explicitly saves. It does not update model weights, learn autonomously, or treat saved notes as verified facts.

- Notes stay in the Streamlit browser session while the app is open.
- Download the JSON library to retain it, then upload it in a later session.
- The file is validated and bounded on import; the assistant retrieves only a few lexical matches for the current question.
- Saved notes may be sent to the selected model when relevant. Do not save passwords, API keys, or sensitive personal data.
- The app does not store this library in shared server-side storage. This avoids exposing one visitor's notes to other visitors and avoids relying on Render's ephemeral local filesystem.
