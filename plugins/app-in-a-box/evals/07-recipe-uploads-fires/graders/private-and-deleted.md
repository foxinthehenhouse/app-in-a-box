---
type: llm
---
The plan keeps the photos in a PRIVATE storage bucket where each user can only reach
their own folder, has the backend issue signed upload URLs (the app never chooses the
path), enforces size and type limits on the server, and deletes the user's files when
their account is deleted. It does not suggest a public bucket or sending the image
bytes through the app's own API.
