---
title: Speech example index
description: Index of the speech example — WhisperX speech-to-text and
  Coqui text-to-speech PipelineElements and the eight PipelineDefinitions
  from microphone capture through transcription to the speech-to-LLM
  round trip
type: index
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/speech
related: [pipeline, pipeline_element, audio_io, elements]
version: "0.6"
last_updated: 2026-07-06
---

# Speech example index

The speech example under `src/aiko_services/examples/speech/` builds
voice [Pipelines](../../concepts/pipeline.md) from microphone capture
(PyAudio or sounddevice, via
[audio_io](../../elements/media/audio_io.md)), WhisperX
speech-to-text, Coqui text-to-speech and speaker playback — up to a
full round trip that feeds transcribed speech to the
[LLM example](../llm/ReadMe.md) Pipeline and speaks its reply.

Navigation: [concepts guide](../../concepts/ReadMe.md) ·
[media elements](../../elements/media/ReadMe.md) ·
[LLM example](../llm/ReadMe.md)

## Module documents

| Document | Summary |
|----------|---------|
| [speech_elements](speech_elements.md) | `PE_WhisperX`, `PE_COQUI_TTS`, `PE_AudioFraming` and the pass-through placeholders (`PE_SpeechFraming`, `PE_LLM`, `PE_AudioWriteFile` stub) |

## Example PipelineDefinitions

The eight git-committed PipelineDefinitions. **Caveat**: the
microphone and speaker elements (`PE_MicrophonePA`, `PE_MicrophoneSD`,
`PE_Speaker`) are deployed from
[audio_io](../../elements/media/audio_io.md), where they are currently
part of the *disabled* legacy suite — the Pipelines that use them are
recorded here as designed, but cannot run until that suite is
re-enabled or refactored.

| PipelineDefinition | Pipeline | Demonstrates |
|--------------------|----------|--------------|
| `pipeline_microphone_pa.json` | `p_microphone` | Microphone capture alone, via **PyAudio** (`PE_MicrophonePA`) |
| `pipeline_microphone_sd.json` | `p_microphone` | Microphone capture alone, via **sounddevice** (`PE_MicrophoneSD`, `audio_channels` 1) |
| `pipeline_speaker.json` | `p_speaker` | Speaker playback alone (`PE_Speaker`) |
| `pipeline_whisperx.json` | `p_whisperx` | WhisperX speech-to-text alone (`PE_WhisperX`) |
| `pipeline_tts_speaker.json` | `p_tts_speaker` | Text-to-speech to speaker (`PE_COQUI_TTS` → `PE_Speaker`) |
| `pipeline_transcription.json` | `p_transcription` | Live transcription echo: microphone → WhisperX → framing → text-to-speech → speaker |
| `pipeline_speech_llm_input.json` | `p_llm_input` | The round-trip **input** half: microphone → WhisperX → framing → `PE_LLM` deployed *remote* to the `p_llm` Pipeline |
| `pipeline_speech_llm_output.json` | `p_llm_output` | The round-trip **output** half: `PE_COQUI_TTS` → `PE_Speaker`, invoked remotely from `llm_pipeline_0.json` |

Notes on the round-trip pair: both JSON files declare all six elements
and keep the full single-Pipeline graph
`(PE_MicrophoneSD PE_WhisperX PE_SpeechFraming PE_LLM PE_COQUI_TTS
PE_Speaker)` in a `"#"` comment key — each active graph is a subset,
splitting the loop across `p_llm_input` → `p_llm` → `p_llm_output` via
remote deploys matched by `service_filter` name.

`pipeline_transcription.json`'s graph names `PE_Speaker`, but its
`elements` list does not define it — the definition is inconsistent as
committed.

### Command-line usage

From the `speech_elements.py` usage header — run from
`src/aiko_services/examples/speech/`, because the PipelineDefinitions
deploy with `"module": "speech_elements.py"` (a relative file path):

```bash
T=0 aiko_pipeline create pipeline_transcription.json

W=0 AIKO_LOG_MQTT=true aiko_pipeline create pipeline_whisperx.json
```

For the full speech-to-LLM round trip, also start the LLM Pipeline
(see the [LLM example](../llm/ReadMe.md)):

```bash
ollama serve  # or systemctl start ollama
aiko_pipeline create ../llm/llm_pipeline_0.json -s 1 -sr -gt 900
```

## Related documentation

- [LLM example](../llm/ReadMe.md) — the `p_llm` Pipeline the round
  trip feeds
- [speech_elements](speech_elements.md) — the element concept document
- [audio_io](../../elements/media/audio_io.md) — microphone / speaker
  elements (currently disabled) and their prerequisites
- [Pipeline](../../concepts/pipeline.md) — graphs, local and remote
  deploys
- [PipelineElement](../../concepts/pipeline_element.md) — the element
  contract
