# Behavioural Science Daily Brief, audio edition

A private podcast feed. The daily Claude run commits a script to `episodes/`;
GitHub Actions renders it to audio, rebuilds the RSS feed and publishes both
through GitHub Pages. Apple Podcasts follows the feed by URL, so the show never
appears in Apple's directory and is not submitted to it.

Nothing here costs money unless you choose a paid voice.

## What goes where

```
episodes/YYYY-MM-DD.md    the spoken script for one day, written for the ear
samples/sample.md         the passage used to compare candidate voices
scripts/synthesize.py     script to MP3, via piper, ElevenLabs, Google or Azure
scripts/build_feed.py     rebuilds feed.xml from audio/ and episodes/
assets/cover.jpg          3000 x 3000 artwork, required by Apple
audio/                    generated, committed by the workflow
feed.xml                  generated, committed by the workflow
```

## Setting it up

1. Create a repository. It has to be public for GitHub Pages at no cost. Nothing
   in the brief is confidential, and the feed address is unlisted rather than
   secret: `itunes:block` is set, so the show cannot be found through Apple's
   search even in principle. If you would rather it were genuinely private, the
   alternative is a paid host, which we can revisit.

2. Push the contents of this folder to the repository's `main` branch.

3. Settings, Pages, and set Source to **GitHub Actions**.

4. Settings, Actions, General, and under Workflow permissions choose
   **Read and write permissions**. The workflow commits the rendered audio back
   to the repository, and it cannot do that otherwise.

5. Actions tab, **Voice samples**, Run workflow. It renders the sample passage
   through five free British voices and publishes a page where you can play them
   one after another. Takes about five minutes on the first run, less afterwards
   because the voice models are cached.

6. Listen at `https://<your-username>.github.io/<repo>/samples/` and choose.

7. Settings, Secrets and variables, Actions, Variables tab, and set:

   | Variable | Value |
   |---|---|
   | `TTS_ENGINE` | `piper`, `elevenlabs`, `google` or `azure` |
   | `TTS_VOICE` | the voice name from the samples page |
   | `KEEP_DAYS` | optional, defaults to 90 |

8. The feed address is
   `https://<your-username>.github.io/<repo>/feed.xml`. In Apple Podcasts, go to
   Library, the three-dot menu at the top right, **Follow a Show by URL**, and
   paste it. This works on the iPhone directly; it does not need a Mac. Send the
   same address to Endymion.

## Adding a paid voice later

The free voices need no account. If you decide the paid ones are worth it,
add the relevant key under Settings, Secrets and variables, Actions, Secrets:

| Engine | Secret | Also set as a Variable |
|---|---|---|
| ElevenLabs | `ELEVENLABS_API_KEY` | `ELEVENLABS_VOICE_A`, `ELEVENLABS_VOICE_B` for the sample run |
| Google | `GOOGLE_TTS_API_KEY` | |
| Azure | `AZURE_TTS_KEY` | `AZURE_TTS_REGION` |

Then re-run **Voice samples**. Any engine without a key is skipped silently, so
the sample page simply shows more options once a key exists.

## Running costs

GitHub Actions and Pages are free on a public repository. Pages allows 100 GB of
traffic a month; a thirteen-minute episode is about nine megabytes, so two
listeners cost well under a gigabyte a year. `KEEP_DAYS` prunes old audio so the
repository does not grow without limit.

A paid voice is the only real cost. At roughly two thousand words a day,
Google and Azure come to a few pounds a month; ElevenLabs is dearer and better.

## Re-rendering

Actions tab, **Publish episodes**, Run workflow, with *Re-render every episode*
ticked. Use this after changing voice, so the back catalogue matches.

## A note on the writing

The audio script is not the email read aloud. The email carries DOIs, course
tags and bracketed sample sizes, which break the line when spoken. The script
drops the citations to journal and month, rounds the numbers, speaks the course
codes as course names, and moves the Concept of the day to the front where
attention is highest. Both come out of the same research in the same run.
