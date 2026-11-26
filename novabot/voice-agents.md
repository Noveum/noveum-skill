# Voice agents

A voice agent is a phone agent the customer builds and runs on Noveum: it answers calls on a
number bound to it and places outbound calls the user launches. Each save is a new version
of its spec; the latest version answers. Its pages are inputs.viewing views voice (the list),
voice_agent (one agent, resource kind voice_agent) and voice_call (one call, resource kind
voice_call). Read the agent or call with the platform API (GET /api/v1/voice/agents/{id},
GET /api/v1/voice/calls/{id}) before answering about it.

## Creating one

Propose create_voice_agent with:

- name: what the team calls it, written as lowercase letters a-z, digits 0-9, _ and -
  only (renewal_reminder, not "Renewal reminder"), at most 80 characters, not used by
  another live agent.
- language: one of English, Hindi, Hinglish, Kannada, Tamil, Telugu, Marathi, Gujarati,
  Bengali, Arabic.
- systemPrompt: who the agent is, what it does on a call and what it must never do. Keep it
  under 2,000 characters so the approval card can show it in full; the user can extend it in
  the builder afterwards.
- greeting (optional): the first thing the agent says when the call is answered. Without
  one the model opens the call itself.
- voiceId (optional): only an id from GET /api/v1/voice/voices?tts=<model>. Without one a
  default voice for the language is picked. Telugu, Marathi, Gujarati and Bengali have no
  voice in the catalog yet, so creating an agent in those languages fails; say so instead of
  retrying.

It uses the default speech recognition, language and speech models, and lands in the chat's
project unless you pass projectId. After it runs, link the user to the agent so they can
review it.

Ask for what you cannot infer, such as what the agent is for and the language, before
proposing. Do not invent business facts, prices or policies for the system prompt.

## Changing one

Edits are a new version: propose platform_api for POST /api/v1/voice/agents/{id}/versions
with the full spec. Read the current version first and pass its number as baseVersion, so a
save someone else made in the meantime is refused instead of overwritten. The operation's
description lists the spec rules beyond the schema; follow them. Tools, stages, prefetch
lookups and key terms are set this way, not through create_voice_agent.

## Tool tokens

A tool that calls the customer's API with auth has a secret_ref of the form
tool/<lowercased tool name>/auth. Never put a token in the spec, its url or its headers, and
never ask for one in the chat. Set it with platform_api PUT /api/v1/voice/agents/{id}/secrets:
leave the value out and the user types it into the approval card. The user can also set it
on the agent's Tools tab.

## Calls

Launching outbound calls is propose_action with platform_api for
POST /api/v1/voice/agents/{id}/calls. It dials real phone numbers and spends credits, so it
always needs the user's explicit approval on the card: propose it only when the user asks to
call, list the numbers in the summary, and never claim a launch ran before the card was
approved. Proposing never dials. The approved action supplies the idempotencyKey itself, so
replaying the same approved action returns the batch already created and dials nobody new;
do not pass your own key, and never retry a launch you were not told failed. Inbound calls
need a number bound to the agent with POST /api/v1/voice/numbers/{id}/assign. A call's
endReason explains why it ended; read the call before explaining a failure.
