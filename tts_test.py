
#coding=utf-8

'''
requires Python 3.6 or later

pip install asyncio
pip install websockets

'''

import asyncio
import websockets
import uuid
import json
import gzip
import copy
import time
import re
from typing import Optional
import numpy as np
from io import BytesIO
from pydub import AudioSegment

MESSAGE_TYPES = {11: "audio-only server response", 12: "frontend server response", 15: "error message from server"}
MESSAGE_TYPE_SPECIFIC_FLAGS = {0: "no sequence number", 1: "sequence number > 0",
                               2: "last message from server (seq < 0)", 3: "sequence number < 0"}
MESSAGE_SERIALIZATION_METHODS = {0: "no serialization", 1: "JSON", 15: "custom type"}
MESSAGE_COMPRESSIONS = {0: "no compression", 1: "gzip", 15: "custom compression method"}


# version: b0001 (4 bits)
# header size: b0001 (4 bits)
# message type: b0001 (Full client request) (4bits)
# message type specific flags: b0000 (none) (4bits)
# message serialization method: b0001 (JSON) (4 bits)
# message compression: b0001 (gzip) (4bits)
# reserved data: 0x00 (1 byte)
default_header = bytearray(b'\x11\x10\x11\x00')



class SeedTTS:
    def __init__(self, model_name="seedtts", logger=None, voice_type="S_xyiql9xn1", language="en"): # "BV700_streaming" zh_male_shaonianzixin_moon_bigtts zh_male_tiancaitongsheng_mars_bigtts S_1YVDxyQk1 S_xyiql9xn1
        self.appid = "8436361232"
        self.token = "tewoU0HvGBfBCSp6TOc1Neq63WHyUzo5"
        # self.cluster = "volcano_tts"
        self.cluster = "volcano_icl" # 定制声音
        self.voice_type = voice_type
        self.host = "openspeech.bytedance.com"
        self.api_url = f"wss://{self.host}/api/v1/tts/ws_binary"
        self.language = language
        self.logger = logger

    async def text2speech(self, text: str, save: bool = False, output_path: str = "audio_seedtts.wav", 
                      hardware_func=None, first_sentence=True, is_transmitting=False, sentence_id=0) -> Optional[bytes]:
        match = re.match(r'<(.*?)>\s*(.*)', text)
        if match:
            emotion = match.group(1).lower()
            text = match.group(2)
        else:
            emotion = ""
            text = text

        # Prepare the request JSON
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
        submit_request_json = copy.deepcopy(request_json)
        submit_request_json["audio"]["voice_type"] = self.voice_type
        submit_request_json["request"]["reqid"] = str(uuid.uuid4())
        submit_request_json["request"]["operation"] = "submit"
        payload_bytes = str.encode(json.dumps(submit_request_json))
        payload_bytes = gzip.compress(payload_bytes)  # Compress the payload
        full_client_request = bytearray(default_header)
        full_client_request.extend((len(payload_bytes)).to_bytes(4, 'big'))  # Payload size (4 bytes)
        full_client_request.extend(payload_bytes)  # Add payload to the request
        header = {"Authorization": f"Bearer; {self.token}"}
        tts_start = time.time()

        # Function to handle the WebSocket connection and process the response
        async def handle_connection(first_sentence, save, file_to_save=None, hardware_func=None, is_transmitting=False, sentence_info=""):
            async with websockets.connect(self.api_url, extra_headers=header, ping_interval=None) as ws:
                await ws.send(full_client_request)
                while True:
                    res = await ws.recv()
                    if save:
                        done = self.parse_response(res, file_to_save)
                    else:
                        done = await self.parse_response_play(res, hardware_func, is_transmitting=is_transmitting, sentence_info=sentence_info, first_sentence=first_sentence, tts_start=tts_start)    
                    if first_sentence and done != "size0":
                    # if done != "size0":
                        if self.logger:
                            self.logger.debug(f"[Time delay measurements]: [TTS API delay for first sentence is {(time.time() - tts_start):.4f}]")
                    if done and done != "size0":
                        if save:
                            file_to_save.close()
                        break
                # print("\nclosing the connection...")

        # Try to execute the request with the retry mechanism
        sentence_info = {"sentence_id":sentence_id, "text":text}
        try:
            if save:
                print('save', save)
                file_to_save = open(output_path, "wb")

                # First attempt
                try:
                    await handle_connection(first_sentence, save=True, file_to_save=file_to_save, is_transmitting=is_transmitting, sentence_info=sentence_info)
                except Exception as e:
                    print(f"First attempt failed: {e}")
                    print("Retrying the request...")

                    # Retry attempt
                    try:
                        await handle_connection(first_sentence, save=True, file_to_save=file_to_save, is_transmitting=is_transmitting, sentence_info=sentence_info)
                    except Exception as retry_error:
                        print(f"Second attempt failed: {retry_error}")
                        raise Exception(f"Both attempts failed: {retry_error}")

            else:
                # First attempt for play mode
                try:
                    await handle_connection(first_sentence, save=False, hardware_func=hardware_func, is_transmitting=is_transmitting, sentence_info=sentence_info)
                except Exception as e:
                    print(f"First attempt failed: {e}")
                    print("Retrying the request...")

                    # Retry attempt
                    try:
                        await handle_connection(first_sentence, save=False, hardware_func=hardware_func, sentence_info=sentence_info)
                    except Exception as retry_error:
                        print(f"Second attempt failed: {retry_error}")
                        raise Exception(f"Both attempts failed: {retry_error}")

            return first_sentence

        except Exception as final_error:
            print(f"Both attempts failed with error: {final_error}")
            raise final_error

    async def text2speech_generator(self, text: str, first_sentence=True, is_transmitting=False) -> Optional[bytes]:
        tts_start = time.time()
        first_time = None
        match = re.match(r'<(.*?)>\s*(.*)', text)
        if match:
            emotion = match.group(1).lower()
            text = match.group(2)
           
        else:
            emotion = ""
            text = text
        # print('emotion',emotion)
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
                "encoding": "wav", # pcm格式会有杂音，而且很慢。wav不支持流式
                "speed_ratio": 1.0,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
                "emotion": emotion,
                "rate": 16000,
                # "language":self.language
            },
            "request": {
                "reqid": str(uuid.uuid4()),
                "text": text,
                "text_type": "plain",
                "operation": "submit",
            }
        }
        submit_request_json = copy.deepcopy(request_json)
        submit_request_json["audio"]["voice_type"] = self.voice_type
        submit_request_json["request"]["reqid"] = str(uuid.uuid4())
        submit_request_json["request"]["operation"] = "submit"
        payload_bytes = str.encode(json.dumps(submit_request_json))
        payload_bytes = gzip.compress(payload_bytes)  # if no compression, comment this line
        full_client_request = bytearray(default_header)
        full_client_request.extend((len(payload_bytes)).to_bytes(4, 'big'))  # payload size(4 bytes)
        full_client_request.extend(payload_bytes)  # payload
        # print("\n------------------------ test 'submit' -------------------------")
        # print("request json: ", submit_request_json)
        # print("\nrequest bytes: ", full_client_request)
        header = {"Authorization": f"Bearer; {self.token}"}

        async with websockets.connect(self.api_url, extra_headers=header, ping_interval=None) as ws:
            await ws.send(full_client_request)
            try:
                while True:
                    res = await ws.recv()
                    protocol_version = res[0] >> 4
                    header_size = res[0] & 0x0f
                    message_type = res[1] >> 4
                    message_type_specific_flags = res[1] & 0x0f
                    serialization_method = res[2] >> 4
                    message_compression = res[2] & 0x0f
                    reserved = res[3]
                    header_extensions = res[4:header_size*4]
                    payload = res[header_size*4:]
                    # print(f"            Protocol version: {protocol_version:#x} - version {protocol_version}")
                    # print(f"                 Header size: {header_size:#x} - {header_size * 4} bytes ")
                    # print(f"                Message type: {message_type:#x} - {MESSAGE_TYPES[message_type]}")
                    # print(f" Message type specific flags: {message_type_specific_flags:#x} - {MESSAGE_TYPE_SPECIFIC_FLAGS[message_type_specific_flags]}")
                    # print(f"Message serialization method: {serialization_method:#x} - {MESSAGE_SERIALIZATION_METHODS[serialization_method]}")
                    # print(f"         Message compression: {message_compression:#x} - {MESSAGE_COMPRESSIONS[message_compression]}")
                    # print(f"                    Reserved: {reserved:#04x}")
                    if header_size != 1:
                        print(f"           Header extensions: {header_extensions}")
                    if message_type == 0xb:  # audio-only server response
                        sequence_number = int.from_bytes(payload[:4], "big", signed=True)
                        payload_size = int.from_bytes(payload[4:8], "big", signed=False)
                        payload = payload[8:]
                        # print(type(payload),len(payload))
                        # tts_output = np.frombuffer(payload, dtype=np.float32)
                        # tts_output = (tts_output * 32767).astype(np.int16)
                        # wav_output = tts_output.tobytes() # fishspeech, seedtts(pcm)
                        if len(payload) > 0:
                            while True:
                                if is_transmitting:
                                    continue
                                else:
                                    is_transmitting = True
                                    segment = AudioSegment.from_raw(BytesIO(payload),
                                                sample_width=2,
                                                frame_rate=16000,
                                                channels=1)
                                    output_io = BytesIO()
                                    segment.export(output_io, format="wav")
                                    wav_output = output_io.getvalue()
                                    yield wav_output
                                    if not first_time:
                                        first_time = time.time()
                                        print("first_time", first_time)
                                        if first_sentence and self.logger:
                                            self.logger.debug(f"[Time delay measurements]: [TTS API delay for first sentence is {(time.time() - tts_start):.4f}]")
                                    is_transmitting = False
                                    break
                        if sequence_number < 0:
                            return
            except Exception as e:
                self.logger.debug(f"Error occured in tts function: {e}")
                raise e
                    


    async def parse_response_play(self, res, hardware_func, is_transmitting, sentence_info, first_sentence, tts_start):
        protocol_version = res[0] >> 4
        header_size = res[0] & 0x0f
        message_type = res[1] >> 4
        message_type_specific_flags = res[1] & 0x0f
        serialization_method = res[2] >> 4
        message_compression = res[2] & 0x0f
        reserved = res[3]
        header_extensions = res[4:header_size*4]
        payload = res[header_size*4:]
        # print(f"            Protocol version: {protocol_version:#x} - version {protocol_version}")
        # print(f"                 Header size: {header_size:#x} - {header_size * 4} bytes ")
        # print(f"                Message type: {message_type:#x} - {MESSAGE_TYPES[message_type]}")
        # print(f" Message type specific flags: {message_type_specific_flags:#x} - {MESSAGE_TYPE_SPECIFIC_FLAGS[message_type_specific_flags]}")
        # print(f"Message serialization method: {serialization_method:#x} - {MESSAGE_SERIALIZATION_METHODS[serialization_method]}")
        # print(f"         Message compression: {message_compression:#x} - {MESSAGE_COMPRESSIONS[message_compression]}")
        # print(f"                    Reserved: {reserved:#04x}")
        if header_size != 1:
            print(f"           Header extensions: {header_extensions}")
        if message_type == 0xb:  # audio-only server response
            if message_type_specific_flags == 0:  # no sequence number as ACK
                print("                Payload size: 0")
                return "size0"
            else:
                sequence_number = int.from_bytes(payload[:4], "big", signed=True)
                payload_size = int.from_bytes(payload[4:8], "big", signed=False)
                payload = payload[8:]
                # print(f"             Sequence number: {sequence_number}")
                # print(f"                Payload size: {payload_size} bytes")
                first_time = time.time() 
                if hardware_func:
                    await hardware_func(payload, first_time, is_transmitting=is_transmitting, sentence_info=sentence_info)
                    # if first_sentence and self.logger:
                    #     self.logger.debug(f"[Time delay measurements]: [Whole TTS process delay for first sentence is {(time.time() - tts_start):.4f}]")
            if sequence_number < 0:
                return True
            else:
                return False
        elif message_type == 0xf:
            code = int.from_bytes(payload[:4], "big", signed=False)
            msg_size = int.from_bytes(payload[4:8], "big", signed=False)
            error_msg = payload[8:]
            if message_compression == 1:
                error_msg = gzip.decompress(error_msg)
            error_msg = str(error_msg, "utf-8")
            print(f"          Error message code: {code}")
            print(f"          Error message size: {msg_size} bytes")
            print(f"               Error message: {error_msg}")
            return True
        elif message_type == 0xc:
            msg_size = int.from_bytes(payload[:4], "big", signed=False)
            payload = payload[4:]
            if message_compression == 1:
                payload = gzip.decompress(payload)
            print(f"            Frontend message: {payload}")
        else:
            print("undefined message type!")
            return True


    def parse_response(self, res, file):
        print("--------------------------- response ---------------------------")
        # print(f"response raw bytes: {res}")
        protocol_version = res[0] >> 4
        header_size = res[0] & 0x0f
        message_type = res[1] >> 4
        message_type_specific_flags = res[1] & 0x0f
        serialization_method = res[2] >> 4
        message_compression = res[2] & 0x0f
        reserved = res[3]
        header_extensions = res[4:header_size*4]
        payload = res[header_size*4:]
        # print(f"            Protocol version: {protocol_version:#x} - version {protocol_version}")
        # print(f"                 Header size: {header_size:#x} - {header_size * 4} bytes ")
        # print(f"                Message type: {message_type:#x} - {MESSAGE_TYPES[message_type]}")
        # print(f" Message type specific flags: {message_type_specific_flags:#x} - {MESSAGE_TYPE_SPECIFIC_FLAGS[message_type_specific_flags]}")
        # print(f"Message serialization method: {serialization_method:#x} - {MESSAGE_SERIALIZATION_METHODS[serialization_method]}")
        # print(f"         Message compression: {message_compression:#x} - {MESSAGE_COMPRESSIONS[message_compression]}")
        # print(f"                    Reserved: {reserved:#04x}")
        if header_size != 1:
            print(f"           Header extensions: {header_extensions}")
        if message_type == 0xb:  # audio-only server response
            if message_type_specific_flags == 0:  # no sequence number as ACK
                print("                Payload size: 0")
                return False
            else:
                sequence_number = int.from_bytes(payload[:4], "big", signed=True)
                payload_size = int.from_bytes(payload[4:8], "big", signed=False)
                payload = payload[8:]
                # print(f"             Sequence number: {sequence_number}")
                # print(f"                Payload size: {payload_size} bytes")
            file.write(payload)
            if sequence_number < 0:
                return True
            else:
                return False
        elif message_type == 0xf:
            code = int.from_bytes(payload[:4], "big", signed=False)
            msg_size = int.from_bytes(payload[4:8], "big", signed=False)
            error_msg = payload[8:]
            if message_compression == 1:
                error_msg = gzip.decompress(error_msg)
            error_msg = str(error_msg, "utf-8")
            print(f"          Error message code: {code}")
            print(f"          Error message size: {msg_size} bytes")
            print(f"               Error message: {error_msg}")
            return True
        elif message_type == 0xc:
            msg_size = int.from_bytes(payload[:4], "big", signed=False)
            payload = payload[4:]
            if message_compression == 1:
                payload = gzip.decompress(payload)
            print(f"            Frontend message: {payload}")
        else:
            print("undefined message type!")
            return True

from io import BytesIO
from pydub import AudioSegment
import time
import websockets
import asyncio
import numpy as np
import json

class TextToSpeech:
    def __init__(self, api_name, model_name=None, websocket=None, logger=None, chunk_size=512):
        self.api_name = api_name
        self.model_name = model_name
        self.api = self.select_api(api_name, model_name, logger)
        self.websocket = websocket
        self.chunk_size = chunk_size

    def select_api(self, api_name, model_name, logger):
        api_dict = {
            "seedtts":SeedTTS,
        }
        if api_name in api_dict:
            if model_name:
                if logger:
                    return api_dict[api_name](model_name, logger=logger)
                return api_dict[api_name](model_name)
            else:
                if logger:
                    return api_dict[api_name](logger=logger)
                return api_dict[api_name]()
        else:
            raise ValueError(f"Unsupported model name: {api_name}")

    def text2speech(self, text, save=False, hardware_func=None, first_sentence=True, is_transmitting=False, sentence_id=0):
        return self.api.text2speech(text, save=save, hardware_func=hardware_func, first_sentence=first_sentence, is_transmitting=is_transmitting, sentence_id=sentence_id)
    
    
    def text2speech_generator(self, text, first_sentence=True, is_transmitting=False):
        return self.api.text2speech_generator(text, first_sentence=first_sentence, is_transmitting=is_transmitting)
    

    async def hardware_function(self, tts_output, hardware_time1=None, websocket=None, chunk_size=None, is_transmitting=False, is_placehold=False, sentence_info=""):
        # hardware_time1 = time.time()
        if websocket is None:
            websocket = self.websocket
        if chunk_size is None:
            chunk_size = self.chunk_size
        # print("websocket",self.websocket)
        if isinstance(tts_output, np.ndarray):
            print("np.ndarray", is_placehold)
            audio_int16 = (tts_output * 32767).astype(np.int16)
            audio_bytes = audio_int16.tobytes()
            wav_output = AudioSegment.from_raw(BytesIO(audio_bytes),
                                                sample_width=2,
                                                frame_rate=16000,
                                                channels=1,
                                                ).raw_data
        else:
            wav_output = tts_output
            #try:
                #tts_output = np.frombuffer(tts_output, dtype=np.float32)
                #tts_output = (tts_output * 32767).astype(np.int16)
                #wav_output = tts_output.tobytes() # fishspeech, seedtts(pcm)， cosyvoice2
                # note: 从24000转换到22050再用22050播放没有作用
            #except:
                #print('except')
                #wav_output = tts_output
        while True:
            # print("is_transmitting",is_transmitting)
            if is_transmitting:
                continue
            else:
                data = {"type": "tts",
                        "state": "sentence_start",
                        "text": sentence_info['text'],
                        "point": sentence_info['sentence_id']
                    }
                await websocket.send(json.dumps(data))
                is_transmitting = True
                start_web = time.time()
                # print('!!! 转成pcm时间', start_web-hardware_time1) # <1ms
                # print('转成pcm',start_web)
                for i in range(0, len(wav_output), chunk_size):
                    chunk = wav_output[i:i + chunk_size]
                    # await websocket.send('1')
                    if is_placehold:
                        await websocket.send(chunk)
                    else:
                        if i/chunk_size > 0:
                            await websocket.send(chunk)
                    # if i==0:
                    #     print("开始传chunk", time.time())
                    # print(f"Sent chunk of size {len(chunk)} bytes")
                end_web = time.time()
                # print(len(wav_output)//chunk_size)
                # print(f"Web connection Time: {end_web - start_web:.6f} seconds")
                # print('end_web',end_web)
                is_transmitting = False
                data = {"type": "tts",
                        "state": "sentence_end",
                        "point": sentence_info['sentence_id']
                    }
                await websocket.send(json.dumps(data))
                break

    def convert_mp3_to_wav(self, mp3_data):
        # Load MP3 data from the BytesIO object
        audio = AudioSegment.from_mp3(BytesIO(mp3_data))
        # Create BytesIO object for WAV output
        byte_io = BytesIO()
        
        # Export audio as WAV format and store in the BytesIO object
        audio.export(byte_io, format="wav")
        
        # Get data from BytesIO
        byte_data = byte_io.getvalue()
        return byte_data

    def convert_mp3_to_pcm(self, mp3_data):

        audio = AudioSegment.from_mp3(BytesIO(mp3_data))
        audio = audio.set_frame_rate(22050).set_sample_width(2).set_channels(1)
        pcm_data = audio.raw_data
        
        return pcm_data


if __name__ == "__main__":
    # 测试不同的模型
    models_to_test = [
        {"api_name": "seedtts"},
    ]


    async def test(model):
        tts = TextToSpeech(model["api_name"])
        start_time = time.time()
        for string in ["Hello, I'm Newton."]:
            result = await tts.text2speech(
                string,
                save=True
            )
        end_time = time.time()
        latency = end_time - start_time
        print(f"Model: {model['api_name']}")
        print(f"Result: {result}")
        print(f"Latency: {latency:.6f} seconds")
        print("-" * 40)


    async def main():
        # 异步执行所有模型的测试
        for model in models_to_test:
            await test(model)
        # import glob
        # import os
        # input_dir = "/mnt/sda/ym_test/project-i-am/iam"  # 替换为包含音频文件的目录路径
        # output_file = "seedllm.wav"  # 合成后的输出文件名

        # # 获取所有要合并的音频文件
        # audio_files = glob.glob(os.path.join(input_dir, "audio_cosy2_instruct_*.wav"))
        # audio_files.sort()  # 按字母顺序排序

        # # 初始化一个空的 AudioSegment
        # combined_audio = AudioSegment.empty()

        # # 加载每个音频文件并合并
        # for file in audio_files:
        #     print(f"Processing file: {file}")
        #     audio = AudioSegment.from_wav(file)
        #     combined_audio += audio

        # # 保存合成后的音频
        # combined_audio.export(output_file, format="wav")
        # print(f"Successfully merged all files into {output_file}")

    # 运行异步主函数
    asyncio.run(main())
