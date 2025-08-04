# Aiko Services Framework Architecture

This document provides a comprehensive overview of the Aiko Services framework architecture, showing how the key components Pipeline, PipelineElement, DataScheme, and Actor work together.

## Architecture Diagram

```mermaid
graph TB
    %% Core Framework Architecture
    subgraph "Aiko Services Framework"
        direction TB
        
        %% Actor Model Layer
        subgraph "Actor Model Layer"
            Service[Service<br/>Base distributed component]
            Actor[Actor<br/>Message-driven processing]
            Service --> Actor
        end
        
        %% Pipeline Layer
        subgraph "Pipeline Execution Layer"
            Pipeline[Pipeline<br/>Orchestrates processing workflow]
            PipelineElement[PipelineElement<br/>Abstract processing unit]
            PipelineElementImpl[PipelineElementImpl<br/>Concrete implementation]
            
            Pipeline --> PipelineElement
            Actor --> PipelineElement
            PipelineElement --> PipelineElementImpl
        end
        
        %% Data Layer
        subgraph "Data Management Layer"
            DataScheme[DataScheme<br/>Abstract data access interface]
            DataSource[DataSource<br/>Input pipeline element]
            DataTarget[DataTarget<br/>Output pipeline element]
            
            PipelineElementImpl --> DataSource
            PipelineElementImpl --> DataTarget
            DataSource --> DataScheme
            DataTarget --> DataScheme
        end
        
        %% Concrete Implementations
        subgraph "Data Scheme Implementations"
            FileScheme[DataSchemeFile<br/>file://]
            ZMQScheme[DataSchemeZMQ<br/>zmq://]
            RTSPScheme[DataSchemeRTSP<br/>rtsp://]
            TTYScheme[DataSchemeTTY<br/>tty://]
            
            DataScheme --> FileScheme
            DataScheme --> ZMQScheme
            DataScheme --> RTSPScheme
            DataScheme --> TTYScheme
        end
    end
    
    %% External Systems
    subgraph "External Systems"
        MQTT[MQTT Broker<br/>Message transport]
        FileSystem[File System<br/>Local/network storage]
        NetworkStreams[Network Streams<br/>RTSP, ZMQ, etc.]
        Terminal[Terminal/Console<br/>Interactive I/O]
    end
    
    %% Processing Flow
    subgraph "Processing Flow"
        direction LR
        Stream[Stream<br/>stream_id, frame_id]
        Frame[Frame<br/>Data payload + metadata]
        StreamEvent[StreamEvent<br/>OKAY | ERROR | STOP]
        
        Stream --> Frame
        Frame --> StreamEvent
    end
    
    %% Pipeline Definition
    subgraph "Pipeline Configuration"
        PipelineJSON[Pipeline Definition<br/>JSON configuration]
        Graph[Graph Structure<br/>Element connections]
        Parameters[Parameters<br/>Runtime configuration]
        Elements[Element Definitions<br/>Input/output schemas]
        
        PipelineJSON --> Graph
        PipelineJSON --> Parameters
        PipelineJSON --> Elements
    end
    
    %% Connections
    Actor -.->|"MQTT Messages"| MQTT
    FileScheme -.->|"Read/Write"| FileSystem
    ZMQScheme -.->|"ZMQ Sockets"| NetworkStreams
    RTSPScheme -.->|"Video Streams"| NetworkStreams
    TTYScheme -.->|"Interactive I/O"| Terminal
    
    Pipeline -.->|"Loads from"| PipelineJSON
    PipelineElement -.->|"Processes"| Stream
    
    %% Data Flow Example
    subgraph "Example Data Flow"
        direction LR
        DS[DataSource<br/>file://input.txt]
        PE1[ProcessingElement<br/>Transform data]
        PE2[ProcessingElement<br/>Filter results]
        DT[DataTarget<br/>zmq://output:5555]
        
        DS --> PE1
        PE1 --> PE2
        PE2 --> DT
    end
    
    %% Styling
    classDef actor fill:#e1f5fe
    classDef pipeline fill:#f3e5f5
    classDef data fill:#e8f5e8
    classDef external fill:#fff3e0
    classDef flow fill:#fce4ec
    
    class Service,Actor actor
    class Pipeline,PipelineElement,PipelineElementImpl pipeline
    class DataScheme,DataSource,DataTarget,FileScheme,ZMQScheme,RTSPScheme,TTYScheme data
    class MQTT,FileSystem,NetworkStreams,Terminal external
    class Stream,Frame,StreamEvent,DS,PE1,PE2,DT flow
```

## Key Architecture Components

### 1. Actor Model Layer
- **Service**: Provides the base distributed component functionality with service discovery and registration
- **Actor**: Extends Service with message-driven processing capabilities, implementing the Actor Model for distributed computation

### 2. Pipeline Execution Layer
- **Pipeline**: Orchestrates workflow execution and manages collections of PipelineElements
- **PipelineElement**: Abstract base class defining the interface for all processing units
- **PipelineElementImpl**: Concrete implementation providing parameter management, logging, and lifecycle methods

### 3. Data Management Layer
- **DataScheme**: Abstract interface for data access patterns, supporting URL-based routing
- **DataSource**: Specialized pipeline element for reading data from various sources
- **DataTarget**: Specialized pipeline element for writing data to various targets

### 4. Data Scheme Implementations
The framework supports multiple data access protocols through concrete DataScheme implementations:
- **DataSchemeFile** (`file://`): File system access with glob patterns and template naming
- **DataSchemeZMQ** (`zmq://`): ZeroMQ socket communication for distributed messaging
- **DataSchemeRTSP** (`rtsp://`): RTSP video stream processing using GStreamer
- **DataSchemeTTY** (`tty://`): Terminal/console interactive I/O

### 5. Processing Flow
- **Stream**: Contains stream_id, frame_id, and processing state
- **Frame**: Data payload with metadata passed between pipeline elements
- **StreamEvent**: Processing result states (OKAY, ERROR, STOP) that control flow

### 6. Pipeline Configuration
Pipelines are defined through JSON configuration files containing:
- **Graph Structure**: Defines how elements are connected using S-expression syntax
- **Parameters**: Runtime configuration values
- **Element Definitions**: Input/output schemas and deployment information

## Example Pipeline Definition

```json
{
  "version": 0,
  "name": "p_example",
  "runtime": "python",
  "graph": ["(PE_RandomIntegers PE_Add (random: i))"],
  "parameters": { "constant": 1, "delay": 0.0, "limit": 2, "rate": 1.0 },
  "elements": [
    {
      "name": "PE_RandomIntegers",
      "input": [{ "name": "random", "type": "int" }],
      "output": [{ "name": "random", "type": "int" }],
      "deploy": {
        "local": { "module": "aiko_services.examples.pipeline.elements" }
      }
    },
    {
      "name": "PE_Add",
      "input": [{ "name": "i", "type": "int" }],
      "output": [{ "name": "i", "type": "int" }],
      "deploy": {
        "local": { "module": "aiko_services.examples.pipeline.elements" }
      }
    }
  ]
}
```

## Key Features

1. **Distributed Processing**: Components can run locally or across different processes/hosts
2. **Asynchronous Message Passing**: MQTT-based communication between distributed actors
3. **Flexible Data Sources**: URL-based routing to different data access schemes
4. **Graph-based Workflows**: Pipeline elements connected through directed graph structures
5. **Extensible Architecture**: Plugin-based system for adding new element types and data schemes
6. **Real-time Processing**: Low-latency stream processing with frame-by-frame execution

## Integration with External Systems

- **MQTT Broker**: Handles distributed message passing between actors
- **File Systems**: Local and network file access through DataSchemeFile
- **Network Streams**: RTSP video streams, ZMQ sockets for distributed communication
- **Interactive Terminals**: Console I/O for debugging and interactive processing

This architecture enables building complex, distributed data processing workflows for AIoT, Machine Learning, Media streaming, and Robotics applications while maintaining consistent interfaces and message passing semantics.