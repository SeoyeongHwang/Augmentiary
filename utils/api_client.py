import openai
from config.message import DIARY_ANALYSIS_PROMPT
from .tone_manager import ToneManager
from .perspective_manager import PerspectiveManager
from .perspective_agents import PerspectiveAgent

class DiaryAnalyzer:
    def __init__(self, api_key):
        self.client = openai.OpenAI(api_key=api_key)
        self.tone_manager = ToneManager(api_key=api_key)  # ToneManager 인스턴스 생성
        self.perspective_manager = PerspectiveManager(api_key=api_key)
        self.perspective_agent = PerspectiveAgent(api_key=api_key)
    
    def augment_with_openai(self, diary_entry, life_orientation, value, tone):
        """일기를 분석하고 결과를 반환하는 메서드"""
        try:
            tone_example = self.tone_manager.get_random_example(tone)
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": DIARY_ANALYSIS_PROMPT.format(
                        tone=tone,
                        tone_example=tone_example,
                        attitude=life_orientation,
                        value=value,
                        diary=diary_entry
                    )
                }],
                temperature=0.8,
            )
            return response.choices[0].message.content
        except Exception as e:
            raise Exception(f"API 요청 중 오류 발생: {str(e)}")
        
    def augment_with_langchain(self, diary_entry: str, life_orientation: str, value: str, tone: str) -> str:
        """LangChain 에이전트를 사용한 분석"""
        try:
            print("▶ 원본: \n", diary_entry)
            result = self.perspective_manager.augment_from_perspective(
                diary_entry=diary_entry,
                life_orientation=life_orientation,  # 추가
                value=value    
            )
            print("▶ perspective agent 동작 완료")
            try: 
                result = self.tone_manager.refine_with_tone(
                    diary_entry=result, 
                    tone=tone
                )
                print("▶ tone agent 동작 완료")
                print("▶ AI 증강 결과: \n", result)
                return result
            except Exception as e:
                raise Exception(f"tone agent 동작 중 오류 발생: {str(e)}")
        except Exception as e:
            raise Exception(f"perspective agent 동작 중 오류 발생: {str(e)}")
        
    def augment_with_perspective(self, diary_entry: str, life_orientation: str, tone: str) -> str:
        """LangChain 에이전트를 사용한 분석"""
        try:
            print("▶ 원본: \n", diary_entry)
            result = self.perspective_agent.augment_from_perspective(
                diary_entry=diary_entry,
                life_orientation=life_orientation
            )
            print("▶ perspective agent 동작 완료")
            try: 
                result = self.tone_manager.refine_with_tone(
                    diary_entry=result, 
                    tone=tone
                )
                print("▶ tone agent 동작 완료")
                print("▶ AI 증강 결과: \n", result)
                return result
            except Exception as e:
                raise Exception(f"tone agent 동작 중 오류 발생: {str(e)}")
        except Exception as e:
            raise Exception(f"perspective agent 동작 중 오류 발생: {str(e)}")
    
    def augment_diary(self, diary_entry: str, life_orientation: str, value: str, tone: str, method: str = "openai") -> str:
        """통합된 증강 메서드"""
        if method == "openai":
            return self.augment_with_openai(diary_entry, life_orientation, value, tone)
        elif method == "langchain":
            return self.augment_with_langchain(diary_entry, life_orientation, value, tone)
        elif method == "perspective":
            return self.augment_with_perspective(diary_entry, life_orientation, tone)
        else:
            raise ValueError(f"지원하지 않는 증강 방법입니다: {method}")