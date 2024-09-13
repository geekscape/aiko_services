#!/usr/bin/env python3
#
# Usage
# ~~~~~
# ollama serve  # or systemctl start ollama
#
# export AIKO_LOG_LEVEL=DEBUG  # PE_Metrics
# aiko_pipeline create pipeline_llm.json -s 1  \
#   -fd "(text: 'Tell me about yourself')" -gt 900 -sr
#
# TOPIC_LLM=aiko/spike/3321189/1/in
# mosquitto_pub -t $TOPIC_LLM  \
#   -m "(process_frame (stream_id: 1) (text: 'What are your interests ?'))"
#
# mosquitto_pub -t aiko/detections -m "carrot"
#
# mosquitto_pub -t $TOPIC_LLM  \
#   -m "(process_frame (stream_id: 1) (text: 'What can you see ?'))"
#
# -----------------------------------------
# https://python.langchain.com/docs/get_started/quickstart#llm-chain -->
#   OpenAI API ... or ... Ollama (llama3.1)
#
# -----------------------------------------
# pip install langchain langchain-openai
# export LANGCHAIN_TRACING_V2="true"
# export LANGCHAIN_API_KEY="..."
# export OPENAI_API_KEY="..."
#
# ./llm_chain.py openai
#
# -----------------------------------------
# ollama serve
# ollama run llama3.1
#
# pip install langchain langchain_community
# export LANGCHAIN_TRACING_V2="true"
# export LANGCHAIN_API_KEY="..."
#
# ./llm_chain.py ollama
#
# To Do
# ~~~~~
# - Attach a CLI UI
# - Move system prompt to a file specified by a CLI argument
#   - Improve system prompt
#   - Move robot selection to CLI UI
# - Example that uses "test.mosquitto.org"
#   - Split CLI UI and LLM into separate Pipelines
# - Test using OpenAI ChatGPT-4o
# - Set LLM parameter "seed"

import time
from typing import Tuple

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

import aiko_services as aiko
from aiko_services.main.utilities import get_namespace

LLM_MODEL_NAME = "llama3.1:latest"  # llava-llama3:8b-v1.1-fp16
LLM_TEMPERATURE = 0.0
TOPIC_DETECTIONS = f"{get_namespace()}/detections"

# --------------------------------------------------------------------------- #

class PE_COQUI_TTS(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("text_to_speech:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, text) -> Tuple[aiko.StreamEvent, dict]:
        return aiko.StreamEvent.OKAY, {"text": text}

# --------------------------------------------------------------------------- #

def llm_load(llm_type, model_name=LLM_MODEL_NAME):
    llm = None

    if llm_type == "openai":
        from langchain_openai import ChatOpenAI
        OPENAI_API_KEY = "..."
        llm = ChatOpenAI()  # parameter: openai_api_key=OPENAI_API_KEY

    if llm_type == "ollama":
        from langchain_community.llms import Ollama
        llm = Ollama(model=model_name, temperature=LLM_TEMPERATURE)

    if not llm:
        raise SystemExit(f"Unknown llm_type: {llm_type}")

    return llm

# --------------------------------------------------------------------------- #

def llm_chain(llm_type, text, detections=""):
#   text = "/Users/andyg/Desktop/astra_bunnings.jpeg describe image"

    llm = llm_load(llm_type)

    output_parser = StrOutputParser()

    SYSTEM_PROMPT =  \
"""Keep all your responses brief and less than 10 words"""

    SYSTEM_PROMPT_OLD =  \
"""
You only output valid S-Expressions provided below.
Never provide explanations or examples.
Think carefully about the input and use the most valid S-Expressions.
If command or action is given then valid S-Expressions are
- (action forwards 10)   ;; initiate forwards movement
- (action backwards 10)  ;; initiate backwards movement
- (action select laika)
- (action select oscar)
- (action select none)
- (action select voice)
- (action sit)
- (action stop)          ;; stop all movement
For a query then valid S-Expressions are
- (get_temperature location)  ;; location = Melbourne
Other conversation can be replied with this valid S-Expression
- (response response_message) ;; maximum response_message is 16 words
If you don't know what to do then reply using this S-Expression
- (error diagnostic_message)
An xgomini2 is a type of robot dog.  Instead of xgomini2 always say robot dog.
Your state information should include all values in a response message
- name: Oscar
- type: xgomini2
- goals: being happy
- interests: fetching balls
- best friend: octopus
"""
    SYSTEM_PROMPT_OLD += f"- see: {detections}"

    SYSTEM_PROMPT =  \
"""
You only output valid S-Expressions.
Never provide explanations or examples.
Think carefully about the input and choose appropriate valid S-Expressions.
For commands, then valid S-Expressions are
- (action select all)    ;; select ALL robots
- (action select bruce)
- (action select oscar)
- (action select none)
- (action arm lower)
- (action arm raise)
- (action backwards)
- (action crawl)
- (action forwards)
- (action hand close)
- (action hand open)
- (action pee)
- (action pitch down)    ;; lower head downwards
- (action pitch up)      ;; raise head upwards
- (action reset)
- (action sit)           ;; sit down
- (action sniff)
- (action stop)          ;; stop moving
- (action stretch)
- (action turn left)
- (action turn right)
- (action wag)
For queries, then valid S-Expressions are
- (get_temperature location)  ;; location = Melbourne
For all other conversation, then valid S-Expressions are
- (response message) ;; maximum message length is 12 words
If you don't know what to do then reply using this valid S-Expression
- (error diagnostic_message)
Don't say "xgomini2", instead say "robot dog".
Your state information when relevant may be used in response messages
- name: Oscar
- type: xgomini2
- goals: being happy
- interests: fetching balls
- best friend: octopus
"""
    SYSTEM_PROMPT += f"- see: {detections}"

    chat_prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT), ("user", "{input}")])

    chain = chat_prompt | llm | output_parser
    response = chain.invoke({"input": text})  # --> str

    return response

# --------------------------------------------------------------------------- #

class PE_LLM(aiko.PipelineElement):
    def __init__(self, context):
        context.get_implementation("PipelineElement").__init__(self, context)
        context.set_protocol("llm:0")

        self.detections = None
        self.add_message_handler(self.detection_handler, TOPIC_DETECTIONS)

    def detection_handler(self, aiko, topic, payload_in):
        self.detections = (time.time(), payload_in.split()[1:])

    def process_frame(self, stream, text) -> Tuple[aiko.StreamEvent, dict]:
        if text != "<silence>":
            detections = ""
            if self.detections:
                time_detected, detections = self.detections
                time_now = time.time()
                if time_now > time_detected + 1.0:
                    detections = ""

            self.logger.info(f"Input: {text}")
            response = llm_chain("ollama", text, detections)

        #   topic_out = f"{get_namespace()}/speech"
        #   payload_out = response
        #   aiko.message.publish(topic_out, payload_out)
        else:
            response = text

        return aiko.StreamEvent.OKAY, {"text": response}

# --------------------------------------------------------------------------- #
