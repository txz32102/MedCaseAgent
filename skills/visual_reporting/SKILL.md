---
name: visual_reporting
description: Integrate medical images conservatively and consistently.
when_to_use: Use when case folders include figures or imaging.
---
Visual rules:
- Use only the images listed in the image index.
- Embed figures with real Markdown image syntax: `![Figure n](images/<filename>)`.
- Reference image paths exactly as `images/<filename>` inside the Markdown image link.
- Place each figure near the text that interprets it.
- Mention clinically relevant panels in the text before the figure block when labels are visible.
- Follow each image block with a short caption, preferably `> **Figure n:** ...`.
- Captions should not introduce findings unsupported by the source record or visible image.
- If image content is ambiguous, describe it cautiously instead of over-reading it.
