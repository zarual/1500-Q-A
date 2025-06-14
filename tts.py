#coding=utf-8

'''
SeedTTS - Version without pydub dependency for Python 3.13 compatibility
requires Python 3.6 or later

pip install asyncio websockets numpy wave
'''

import asyncio
import websockets
import uuid
import json
import gzip
import copy
import time
import re
import wave
import struct
from typing import Optional
import numpy as np
from io import BytesIO

# Protocol constants
MESSAGE_TYPES = {11: "audio-only server response", 12: "frontend server response", 15: "error message from server"}
MESSAGE_TYPE_SPECIFIC_FLAGS = {0: "no sequence number", 1: "sequence number > 0", 2: "last message from server (seq < 0)", 3: "sequence number < 0"}
MESSAGE_SERIALIZATION_METHODS = {0: "no serialization", 1: "JSON", 15: "custom type"}
MESSAGE_COMPRESSIONS = {0: "no compression", 1: "gzip", 15: "custom compression method"}

# Default header for requests
default_header = bytearray(b'\x11\x10\x11\x00')

def pcm_to_wav(pcm_data, sample_rate=16000, channels=1, sample_width=2):
    """Convert PCM data to WAV format without pydub"""
    wav_buffer = BytesIO()
    
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    
    return wav_buffer.getvalue()

class SeedTTS:
    def __init__(self, voice_type="S_xyiql9xn1", language="en", logger=None):
        """
        Initialize SeedTTS
        
        Voice options:
        - "S_xyiql9xn1" (English voice)
        - "zh_male_shaonianzixin_moon_bigtts" (Chinese boy voice)
        - "zh_male_tiancaitongsheng_mars_bigtts" (Chinese boy voice)
        """
        self.appid = "8436361232"
        self.token = "tewoU0HvGBfBCSp6TOc1Neq63WHyUzo5"
        self.cluster = "volcano_icl"  # For custom voices
        self.voice_type = voice_type
        self.host = "openspeech.bytedance.com"
        self.api_url = f"wss://{self.host}/api/v1/tts/ws_binary"
        self.language = language
        self.logger = logger

    async def text2speech(self, text: str, save: bool = False, output_path: str = "audio_seedtts.wav", 
                         hardware_func=None, first_sentence=True, sentence_id=0) -> Optional[bytes]:
        """Convert text to speech"""
        # Parse emotion tags like <happy> text
        match = re.match(r'<(.*?)>\s*(.*)', text)
        if match:
            emotion = match.group(1).lower()
            text = match.group(2)
        else:
            emotion = ""

        # Prepare request
        request_json = {
            "app": {
                "appid": self.appid,
                "token": self.token,
                "cluster": self.cluster
            },
            "user": {
                "uid": "388808087185088"
            },
            "audio": {
                "voice_type": self.voice_type,
                "encoding": "wav",
                "speed_ratio": 1.0,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
                "rate": 16000,
            },
            "request": {
                "reqid": str(uuid.uuid4()),
                "text": text,
                "text_type": "plain",
                "operation": "submit",
            }
        }

        # Add emotion if present
        if emotion:
            request_json["audio"]["emotion"] = emotion

        # Prepare binary request
        payload_bytes = str.encode(json.dumps(request_json))
        payload_bytes = gzip.compress(payload_bytes)
        full_client_request = bytearray(default_header)
        full_client_request.extend((len(payload_bytes)).to_bytes(4, 'big'))
        full_client_request.extend(payload_bytes)
        
        header = {"Authorization": f"Bearer; {self.token}"}
        tts_start = time.time()

        # Store audio data for saving
        audio_data = bytearray()

        # WebSocket connection handler
        async def handle_connection():
            nonlocal audio_data
            async with websockets.connect(self.api_url, extra_headers=header, ping_interval=None) as ws:
                await ws.send(full_client_request)
                
                while True:
                    res = await ws.recv()
                    
                    if save:
                        done, chunk = self.parse_response_save(res)
                        if chunk:
                            audio_data.extend(chunk)
                    else:
                        done = await self.parse_response_play(res, hardware_func, first_sentence, tts_start, sentence_id, text)
                    
                    if done and done != "size0":
                        break
                
                # # Save audio data if requested
                # if save and audio_data:
                #     # Convert PCM to WAV and save
                #     wav_data = pcm_to_wav(audio_data)
                #     with open(output_path, 'wb') as f:
                #         f.write(wav_data)
                        
                if save:
                    print(f"DEBUG: length of audio_data = {len(audio_data)}") 
                if audio_data:
                    wav_data = pcm_to_wav(audio_data)
                    with open(output_path, 'wb') as f:
                        f.write(wav_data)
                else:
                    print("DEBUG: audio_data is empty, skipping file write.")

        # Execute with retry
        try:
            await handle_connection()
            return first_sentence
        except Exception as e:
            if self.logger:
                self.logger.error(f"TTS request failed: {e}")
            # Retry once
            try:
                await handle_connection()
                return first_sentence
            except Exception as retry_error:
                raise Exception(f"TTS failed after retry: {retry_error}")

    async def parse_response_play(self, res, hardware_func, first_sentence, tts_start, sentence_id, text):
        """Parse response for playback mode"""
        protocol_version = res[0] >> 4
        header_size = res[0] & 0x0f
        message_type = res[1] >> 4
        message_type_specific_flags = res[1] & 0x0f
        message_compression = res[2] & 0x0f
        payload = res[header_size*4:]

        if message_type == 0xb:  # audio-only server response
            if message_type_specific_flags == 0:
                return "size0"
            
            sequence_number = int.from_bytes(payload[:4], "big", signed=True)
            payload_size = int.from_bytes(payload[4:8], "big", signed=False)
            audio_payload = payload[8:]
            
            if hardware_func and len(audio_payload) > 0:
                sentence_info = {"sentence_id": sentence_id, "text": text}
                await hardware_func(audio_payload, time.time(), sentence_info=sentence_info)
                
                if first_sentence and self.logger:
                    self.logger.debug(f"TTS first sentence delay: {(time.time() - tts_start):.4f}s")
            
            return sequence_number < 0
            
        elif message_type == 0xf:  # error message
            code = int.from_bytes(payload[:4], "big", signed=False)
            msg_size = int.from_bytes(payload[4:8], "big", signed=False)
            error_msg = payload[8:]
            if message_compression == 1:
                error_msg = gzip.decompress(error_msg)
            error_msg = str(error_msg, "utf-8")
            
            if self.logger:
                self.logger.error(f"TTS Error {code}: {error_msg}")
            else:
                print(f"TTS Error {code}: {error_msg}")
            return True

        return False

    def parse_response_save(self, res):
        """Parse response for save mode"""
        header_size = res[0] & 0x0f
        message_type = res[1] >> 4
        message_type_specific_flags = res[1] & 0x0f
        payload = res[header_size*4:]

        if message_type == 0xb:  # audio-only server response
            if message_type_specific_flags == 0:
                return False, None
            
            sequence_number = int.from_bytes(payload[:4], "big", signed=True)
            audio_payload = payload[8:]
            
            return sequence_number < 0, audio_payload
        
        return True, None  # End on error or other message types


class TextToSpeech:
    """Simplified TTS wrapper"""
    def __init__(self, voice_type="S_xyiql9xn1", language="en", logger=None, websocket=None, chunk_size=512):
        self.api = SeedTTS(voice_type=voice_type, language=language, logger=logger)
        self.websocket = websocket
        self.chunk_size = chunk_size

    async def text2speech(self, text, save=False, output_path: str = "audio_seedtts.wav", hardware_func=None, first_sentence=True, sentence_id=0):
        """Convert text to speech"""
        return await self.api.text2speech(
            text,
            save=save,
            output_path=output_path,
            hardware_func=hardware_func,
            first_sentence=first_sentence,
            sentence_id=sentence_id
        )

    async def hardware_function(self, tts_output, hardware_time1=None, websocket=None, 
                              chunk_size=None, sentence_info=""):
        """Handle audio output to websocket"""
        if websocket is None:
            websocket = self.websocket
        if chunk_size is None:
            chunk_size = self.chunk_size

        # Convert audio data to proper format
        if isinstance(tts_output, np.ndarray):
            audio_int16 = (tts_output * 32767).astype(np.int16)
            wav_output = audio_int16.tobytes()
        else:
            wav_output = tts_output

        # Send audio data via websocket
        if websocket:
            # Send start signal
            data = {
                "type": "tts",
                "state": "sentence_start",
                "text": sentence_info.get('text', ''),
                "point": sentence_info.get('sentence_id', 0)
            }
            await websocket.send(json.dumps(data))

            # Send audio chunks
            for i in range(0, len(wav_output), chunk_size):
                chunk = wav_output[i:i + chunk_size]
                if i > 0:  # Skip first empty chunk
                    await websocket.send(chunk)

            # Send end signal
            data = {
                "type": "tts",
                "state": "sentence_end",
                "point": sentence_info.get('sentence_id', 0)
            }
            await websocket.send(json.dumps(data))


# Example usage
async def main():
    """Test the TTS with boy voice"""
    
    # Available boy voices:
    boy_voices = [
        "zh_male_shaonianzixin_moon_bigtts",  # Chinese boy voice 1
        "zh_male_tiancaitongsheng_mars_bigtts",  # Chinese boy voice 2
        "S_xyiql9xn1" # English boy voice
    ]

    
    # English boy voice
    tts = TextToSpeech(
    voice_type="S_xyiql9xn1",
    language="en"
    )   
    
    # Test texts - Change these to your desired content
    test_texts = [
        # "你好，我是一个小男孩的声音。",  # Chinese text for boy voice
        "<happy> Hello, I'm Newton, how are you today?",  # English text
    ]
    
    start_time = time.time()
    
    for i, text in enumerate(test_texts):
        print(f"Processing text {i+1}: {text}")
        try:
            result = await tts.text2speech(
                text,
                save=True,
                output_path=f"boy_voice_output_{i+1}.wav"
            )
            print(f"✓ Saved to: boy_voice_output_{i+1}.wav")
        except Exception as e:
            print(f"✗ Failed to process text {i+1}: {e}")
    
    end_time = time.time()
    print(f"Total processing time: {end_time - start_time:.2f} seconds")


if __name__ == "__main__":
    asyncio.run(main())