---
title: Google Colab example index
description: Index of the Google Colab integration example — browser
  camera / microphone / speaker to Aiko Services Pipelines running in a
  Colab notebook kernel, with speech-to-text, text-to-speech and YOLOE
  detection PipelineDefinitions
type: index
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/colab
related: [pipeline, pipeline_element, data_source_target, scheme]
version: "0.6"
last_updated: 2026-07-06
---

# Google Colab example index

The `src/aiko_services/examples/colab/` package connects a web
browser — camera, microphone and speaker — to Aiko Services
[Pipelines](../../concepts/pipeline.md) running inside a Google Colab
notebook kernel. JavaScript in the notebook output captures media and
calls registered Python kernel callbacks, which inject Frames into a
Pipeline; results (processed images, synthesised speech, chat
messages) flow back to the browser or out to a discovered chat
server. This makes free Google Colab GPUs usable for interactive
Aiko Services demonstrations: YOLOE object detection, faster-whisper
speech-to-text and coqui-tts text-to-speech.

Navigation: [concepts guide](../../concepts/ReadMe.md) ·
[media elements index](../../elements/media/ReadMe.md)

The package `__init__.py` exports `AudioPassThrough`,
`ConvertDetections`, `ChatServer`, `MQTTPublish` and `VideoReadColab`
from `elements.py`, and `DataSchemeColab` from `scheme_colab.py`
(importing the package registers the `colab://` DataScheme).
`SpeechToText` and `TextToSpeech` are intentionally *not* re-exported
— they are deployed by module path, keeping their heavy model
dependencies out of the package import. `colab_io.py` is imported
directly by notebook cells, not via the package.

## Module documents

| Document | Summary |
|----------|---------|
| [colab_io](colab_io.md) | Notebook glue — kernel callbacks, the camera + audio widget, and audio Frame injection via `pipeline.create_frame()` |
| [elements](elements.md) | The PipelineElements — `AudioPassThrough`, `ConvertDetections`, `ChatServer` / `MQTTPublish`, `SpeechToText`, `TextToSpeech`, `VideoReadColab` |
| [scheme_colab](scheme_colab.md) | `colab://` DataScheme — browser web camera as a DataSource; work-in-progress browser loopback |

## Example PipelineDefinitions

The seven git-committed PipelineDefinitions under
`src/aiko_services/examples/colab/pipelines/`. The audio pipelines
are driven from a notebook via [colab_io](colab_io.md); the YOLOE
pipelines additionally use the YoloDetector element from
`src/aiko_services/examples/yolo/yolo.py` (not yet documented) and
[ImageOverlay](../../elements/media/image_io.md).

| PipelineDefinition | Module document(s) | Purpose |
|--------------------|--------------------|---------|
| `colab_audio_pipeline_0.json` | [elements](elements.md), [colab_io](colab_io.md) | Audio smoke test: browser microphone -> `AudioPassThrough` -> browser speaker |
| `colab_audio_pipeline_1.json` | [elements](elements.md), [colab_io](colab_io.md) | Speech-to-text: `SpeechToText` -> `Expression` (text -> message) -> `MQTTPublish` to chat channel `llm` |
| `colab_audio_pipeline_2.json` | [elements](elements.md), [colab_io](colab_io.md) | Voice round-trip: `SpeechToText` -> `Expression` -> `MQTTPublish` -> `TextToSpeech` back to the browser speaker |
| `colab_ds_pipeline_0.json` | [scheme_colab](scheme_colab.md), [elements](elements.md) | `VideoReadColab` DataSource with `data_sources` `(colab://)` — work-in-progress; the committed deploy module path is wrong (see [scheme_colab](scheme_colab.md)) |
| `colab_pipeline_0.json` | [elements](elements.md), [colab_io](colab_io.md) | YOLOE detection: injected browser images -> `YoloDetector` -> `ImageOverlay` (no DataSource element — frames are pushed by the notebook) |
| `colab_pipeline_1.json` | [elements](elements.md) | Local-webcam variant (runs *outside* Google Colab): [VideoReadWebcam](../../elements/media/webcam_io.md) -> `YoloDetector` -> `ConvertDetections` -> `MQTTPublish` (channel `yolo`) and `ImageOverlay` |
| `colab_pipeline_2.json` | [elements](elements.md), [colab_io](colab_io.md) | As `colab_pipeline_1.json` but sourceless: injected browser images -> detection names published to chat channel `yolo`, overlaid images returned |

Note: the image-injection path in [colab_io](colab_io.md) is currently
a loopback stub, so `colab_pipeline_0.json` and
`colab_pipeline_2.json` document the *intended* browser-camera flow;
today only the audio pipelines receive browser Frames end-to-end.

## Requirements

`requirements.txt` pins the notebook-side dependencies beyond
Aiko Services itself: `faster-whisper` (speech-to-text), `coqui-tts`
and `coqui-tts-trainer` (text-to-speech), `torch` / `torchaudio`,
`transformers`, `opencv-python`, `numpy`, `av`, `sounddevice`,
`soundfile` and `ipython`. Install them in the Google Colab runtime
before creating the audio pipelines; `ffmpeg` must also be on the
`PATH` (it is, on standard Colab images).

## Related documentation

- [Pipeline](../../concepts/pipeline.md) — PipelineDefinitions,
  graphs and `create_frame()`
- [PipelineElement](../../concepts/pipeline_element.md) — the element
  contract
- [DataSource / DataTarget](../../concepts/data_source_target.md) —
  the design `VideoReadColab` follows
- [DataScheme](../../concepts/scheme.md) — URL-selected transports;
  `colab://` registration
- [Stream](../../concepts/stream.md) — stream / frame lifecycle
- [Media elements index](../../elements/media/ReadMe.md) —
  `ImageOverlay`, `VideoReadWebcam` and the fully implemented
  DataSchemes to compare against
- [Utility elements](../../elements/utilities/elements.md) —
  `Expression`, used in the audio pipelines
