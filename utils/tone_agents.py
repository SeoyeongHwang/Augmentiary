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

        일기:
        ```
        {diary_entry}
        ```

        '{tone}' 톤의 예시:
        "{tone_example}"

        주어진 일기의 내용은 유지하되, 예시를 참고하여 '{tone}' 톤을 다음 측면에서 적용해 주세요:
        - 묘사의 깊이
        - 표현의 가벼움
        - 주로 사용되는 어투
        - (예시에 포함된 경우) 이모티콘, 아스키 이모지, 웃음 문자(예: 'ㅋㅋ', 'ㅎㅎ') 등의 활용

        유의사항:
        - 원본 일기의 사실(사건, 행동, 감정)을 유지하세요.
        - 필요 시 가독성을 위해 적절한 줄바꿈을 추가하세요.
        - 표현의 일관성과 자연스러움을 유지하세요.

        {format_instructions}
        """
    )
)

my_tone_template = PromptTemplate(
    input_variables=["diary_entry", "original_diary_entry"],
    template=(
        """
        당신은 글쓰기 전문가입니다. '확장된 글'을 '원본 글'을 쓴 사람이 작성한 것처럼 다듬어야 합니다. 

        '확장된 글'을 '원본 글'과 비교하여 동일한 부분은 유지하되, 다른 부분에 한해서 '원본 글'의 표현을 반영해 자연스럽게 다듬으세요:
        - 어휘와 단어 선택
        - 문장의 길이와 구조
        - 전반적인 어조

        유의사항:
        - 원본 글의 내용은 그대로 유지되고, 추가된 부분의 '표현이나 어휘'가 다듬어진 상태여야 합니다.
        - 수정 사항이 없는 경우 원본 글을 반환하세요.

        원본 글:
        ```
        {original_diary_entry}
        ```

        확장된 글:
        ```
        {diary_entry}
        ```

        {format_instructions}
        """
    )
)

class ToneAugmentResult(BaseModel):
    diary_entry: str = Field(description="증강된 일기 내용")

class ToneAgent:
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
        json_path = Path(__file__).parent.parent / 'config' / 'tone_examples_v2.json'
        with open(json_path, 'r', encoding='utf-8') as f:
            all_examples = json.load(f)
        
        # 톤에 따라 예시를 필터링
        tone_keys = ["warm", "calm", "funny", "emotional"]
        filtered_examples = {tone: examples for tone, examples in all_examples.items() if tone in tone_keys}
        return filtered_examples
    
    def get_random_example(self, tone: str) -> str:
        """특정 톤의 랜덤 예시 반환"""
        if tone not in self.examples:
            raise ValueError(f"'{tone}'에 해당하는 예시를 찾을 수 없습니다.")
        chosen = random.choice(self.examples[tone])
        print("톤 예시: ", chosen)
        return chosen
    
    def _create_tone_chain(self, tone: str):
        """글 톤을 다듬는 체인 생성"""
        if tone=="my_tone":
            return my_tone_template | self.llm | self.tone_parser
        else:
            return tone_template | self.llm | self.tone_parser

    def refine_with_tone(self, diary_entry: str, original_diary_entry: str, tone: str) -> str:
        try:
            if tone=="my_tone":
                
                tone_chain = self._create_tone_chain(tone)
                tone_result = tone_chain.invoke({
                    "diary_entry": diary_entry,
                    "original_diary_entry": original_diary_entry,
                    "format_instructions": self.tone_parser.get_format_instructions()
                })
                
                return diary_entry
            else:
                tone_chain = self._create_tone_chain(tone)
                tone_result = tone_chain.invoke({
                    "diary_entry": diary_entry,
                    "tone": tone,
                    "tone_example": self.get_random_example(tone),
                    "format_instructions": self.tone_parser.get_format_instructions()
                })
                return tone_result.diary_entry
        
        except Exception as e:
            print(f"증강 중 오류 발생: {str(e)}")