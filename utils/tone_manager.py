import json
import random
from pathlib import Path
from langchain.prompts import PromptTemplate
from langchain_community.chat_models import ChatOpenAI
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from typing import Dict, List

tone_template = PromptTemplate(
    input_variables=["diary_entry", "tone", "tone_example"],
    template=(
        """
        당신은 글쓰기 전문가입니다.
        주어진 일기가 포함한 내용은 바꾸지 말되, 묘사의 깊이/표현의 가벼움/주로 사용되는 어투의 측면에서 '{tone}' 톤을 적용해야 합니다.
        필요한 경우, 가독성을 고려한 줄바꿈도 적용해주세요.

        '{tone}' 톤의 예시는 다음과 같습니다: 
        "{tone_example}"
        
        위의 예시를 참고하여, 주어진 일기의 내용에 '{tone}' 톤을 자연스럽게 적용해 주세요.
        에시에 이모티콘, 아스키 이모지, 웃음 문자(e.g. 'ㅋㅋ', 'ㅎㅎ') 등이 포함되어 있다면, 참고해서 적절히 활용하세요:
        ==================
        {diary_entry}
        ==================

        한국어로 응답하세요.
        {format_instructions}
        """
    )
)

class ToneAugmentResult(BaseModel):
    diary_entry: str = Field(description="증강된 일기 내용")

class ToneManager:
    def __init__(self, api_key: str):
        self.examples: Dict[str, List[str]] = self._load_examples()
        self.llm = ChatOpenAI(
            model_name="gpt-4o-mini",
            temperature=0.7,
            openai_api_key=api_key
        )
        self.tone_parser = PydanticOutputParser(pydantic_object=ToneAugmentResult)

    def _load_examples(self) -> Dict[str, List[str]]:
        """톤 예시 JSON 파일 로드"""
        json_path = Path(__file__).parent.parent / 'config' / 'tone_examples.json'
        with open(json_path, 'r', encoding='utf-8') as f:
            all_examples = json.load(f)
        
        # 톤에 따라 예시를 필터링
        return all_examples
    
    def get_random_example(self, tone: str) -> str:
        """특정 톤의 랜덤 예시 반환"""
        if tone not in self.examples:
            raise ValueError(f"'{tone}'에 해당하는 예시를 찾을 수 없습니다.")
        chosen = random.choice(self.examples[tone])
        print("톤 예시: ", chosen)
        return chosen
    
    def _create_tone_chain(self):
        """글 톤을 다듬는 체인 생성"""
        return tone_template | self.llm | self.tone_parser

    def refine_with_tone(self, diary_entry: str, tone: str) -> str:
        try:
            tone_chain = self._create_tone_chain()
            tone_result = tone_chain.invoke({
                "diary_entry": diary_entry,
                "tone": tone,
                "tone_example": self.get_random_example(tone),
                "format_instructions": self.tone_parser.get_format_instructions()
            })
            return tone_result.diary_entry
        except Exception as e:
            raise Exception(f"증강 중 오류 발생: {str(e)}")