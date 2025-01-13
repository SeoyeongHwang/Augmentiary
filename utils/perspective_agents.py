from langchain.prompts import PromptTemplate
from langchain_community.chat_models import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from typing import Dict, List
import json
from pathlib import Path

# 추출 결과 모델 정의
class DiscoveringSteps(BaseModel):
    quotes: str = Field(description="An excerpt from the original diary.")
    new_perspective: str = Field(description="New meaning and insights from a given perspective on an excerpt.")
class DiscoveredResults(BaseModel):
    points: list[DiscoveringSteps] = Field(description="List of extracted excerpts and its interpretations.")
# 증강 결과 모델 정의
class AugmentResult(BaseModel):
    diary_entry: str = Field(description="증강된 일기 내용")



# 첫 번째 프롬프트 템플릿: 관점 발굴
discover_template = PromptTemplate(
    input_variables=["diary_entry", "life_orientation", "life_orientation_desc"],
    template=(
        """
        당신은 {life_orientation} 관점을 통해 세상을 바라보며, 다른 사람들이 새로운 관점과 건설적인 통찰을 발견할 수 있도록 돕는 역할을 수행합니다. 
        {life_orientation_desc}

        사용자는 자신의 경험에 대한 일기를 작성했습니다. 
        사용자는 자신의 일기에 {life_orientation} 관점이 덧대어진 버전을 읽어보고, 새로운 의미과 관점을 고려하고자 합니다. 
        당신의 임무는 일기에서 {life_orientation} 태도를 바탕으로 의미의 재해석이나 인사이트가 필요한 부분을 식별하는 것입니다.

        [작업 지시] 
        1. 사용자의 일기를 읽고 다음 요소를 깊이 이해하세요:
        - 사용자가 표현한 감정과 생각
        - 기술된 사건의 맥락과 배경
        - 암묵적인 고민, 욕구 또는 어려움 
        2. 이러한 이해를 바탕으로, 일기에서 {life_orientation} 관점으로 재해석할 수 있는 부분 1~3개를 식별하세요. 
        3. 각 부분을 {life_orientation} 관점에서 어떻게 바라볼 수 있는지, 이를 통해 어떤 이점을 얻을 수 있는지에 대해 1~3문장으로 설명하세요:
        - 원본 일기의 사실(사건, 행동, 감정, 생각)을 유지하세요.
        - 일기에 드러난 감정과 생각을 존중하고 인정하면서도 건설적인 관점을 부드럽게 소개하세요.
        - 사용자의 고유한 상황을 반영하여 재해석이 적절하고 공감적으로 느껴져야 합니다.

        [결과]
        1. 사용자에 대한 이해 
        2. 식별 결과
            - 일기의 관련 부분 발췌
            - 관점에 근거한 재해석: {life_orientation} 관점에서 해석을 제공하며, 이유와 정당성을 포함.
        
        [일기]
        ```
        {diary_entry}
        ```


        {format_instructions}
        """
    )
)
discover_template_v2 = PromptTemplate(
    input_variables=["diary_entry", "life_orientation", "life_orientation_desc", "highlight"],
    template=(
        """
        당신은 {life_orientation} 관점을 통해 세상을 바라보며, 다른 사람들이 새로운 관점과 건설적인 생각을 발견할 수 있도록 돕는 역할입니다. 
        {life_orientation_desc}
        당신의 임무는 {life_orientation} 시각으로 일기를 읽고, 의미의 재해석이나 인사이트가 필요한 부분을 식별하는 것입니다.

        [작업 지시] 
        1. 사용자의 일기를 읽고 다음 요소를 깊이 이해하세요:
        - 사용자가 표현한 감정과 생각
        - 기술된 사건의 맥락과 배경
        - 암묵적인 고민, 욕구 또는 어려움 

        2. 이러한 이해를 바탕으로, 일기에서 {life_orientation} 관점으로 재해석할 수 있는 부분을 식별하세요. 다음을 고려하세요:

        3. 발견한 새로운 시각이나 해석은 다음을 준수해야 합니다:
        - 원본 일기의 사실(사건, 행동, 감정, 생각)을 유지
        - {highlight}을 강조하되, 너무 거창한 해석은 자제
        - 감정과 생각을 존중하고 인정하면서 건설적인 관점을 부드럽게 소개
        - 사용자의 고유한 상황을 반영하여 적절하고 공감적인 내용 제공

        
        [일기]
        ```
        {diary_entry}
        ```

        {format_instructions}
        """
    )
)

# 두 번째 프롬프트 템플릿: 내용 증강
augment_template = PromptTemplate(
    input_variables=["diary_entry", "life_orientation", "highlight", "relevant_points"],
    template=(
        """
        이 일기의 작성자라고 상상해 보십시오. 당신의 역할은 {life_orientation}인 성찰, 생각, 가능성을 원래 일기에 자연스럽게 통합하면서도 일기의 고유한 문체와 어조를 유지하는 것입니다. 
        최종적으로 완성된 일기는 마치 처음부터 작성자가 직접 쓴 것처럼 읽혀야 하며, 원본에 드러나지 않았던 미묘하면서도 새로운 의미와 관점을 포함해야 합니다.

        [작업 지시]
        1. 일기 원본의 글 스타일 유지하기:
        - 사용되는 표현, 전반적인 문체
        - 문장의 길이와 구조

        2. 제공된 설명에서 영감을 받아 {life_orientation}인 태도로 의미를 해석하고 덧붙이기:
        - 원본 일기의 사실(사건, 행동, 감정)을 유지하세요. 
        - 어조와 흐름을 존중하며 새로운 의미와 재해석을 작성하세요.
        - 발췌된 원본 글을 참고하여, 자연스러운 위치에 확장을 통합하세요.

        3. 추가된 내용이 충족해야 할 조건:
        - {life_orientation}인 관점에서 {highlight}에 집중해야 합니다.
        - 흐름과 감정적 연속성을 해치지 않도록 자연스러워야 합니다.
        - 스스로에게 제안하거나 질문하는 어조를 고려하세요.

        [입력]
        1. 원본 일기:
        ```
        {diary_entry}
        ```
        2. 관련 발췌 및 관점:
        ```
        {relevant_points}
        ```

        {format_instructions}
        """
    )
)
augment_template_v2 = PromptTemplate(
    input_variables=["diary_entry", "life_orientation", "highlight", "relevant_points"],
    template=(
        """
        당신은 이 일기의 작성자가 되어, {life_orientation}적인 관점과 인사이트를 원본 일기에 자연스럽게 통합하는 역할을 합니다. 최종적으로 완성된 일기는 마치 처음부터 작성자가 직접 쓴 것처럼 읽혀야 하며, 원본에 드러나지 않았던 미묘하면서도 새로운 의미와 관점을 포함하여 작성자가 자신의 경험을 다시 돌아볼 수 있어야 합니다.

        [작업 지시]
        1. 원본 일기의 어휘, 문장 구조, 전반적인 어조를 따라하세요.

        2. {life_orientation} 관점에서 의미/관점/시각을 생성할 때:
        - 원본 일기의 사실(사건, 행동, 감정)을 유지하세요.
        - 제시된 발췌문을 참고하여 적절한 위치에 새로운 관점/의미/재해석을 덧붙이세요. 
        - 관점 설명은 그대로 복사하지 말고 영감으로만 삼으십시오.
        - {highlight}에 집중하되, 원본 글의 내러티브, 감정적 연속성을 고려하여 너무 거창하게 쓰지 않도록 합니다.
        - 일상적이고 쉬운 표현을 쓰고 문장길이는 짧게 유지하세요.
        - 스스로에게 제안하거나 질문하는 어조를 사용하세요.

        [입력]
        1. 원본 일기:
        ```
        {diary_entry}
        ```
        2. 관련 발췌 및 관점:
        ```
        {relevant_points}
        ```

        {format_instructions}
        """
    )
)


class PerspectiveAgent:
    def __init__(self, api_key_gpt: str, api_key_claude: str):
        self.life_orientations = self._load_life_orientations()
        self.gpt = ChatOpenAI(
            model_name="gpt-4o",
            temperature=1.0,
            openai_api_key=api_key_gpt
        )
        """
        self.claude = ChatAnthropic(
            model="claude-3-5-haiku-20241022",
            temperature=1.0,
            max_tokens=10000,
            timeout=None,
            max_retries=2,
            api_key=api_key_claude
        )
        """
        self.discover_parser = PydanticOutputParser(pydantic_object=DiscoveredResults)
        self.augment_parser = PydanticOutputParser(pydantic_object=AugmentResult)
    
    
    def _load_life_orientations(self) -> Dict:
        """life_orientations.json 파일에서 관점 정의를 로딩"""
        json_path = Path(__file__).parent.parent / 'config' / 'perspectives.json'
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _create_discover_chain(self):
        """주어진 관점에서 다시 바라볼 포인트를 발견하는 체인 생성"""
        return discover_template_v2 | self.gpt | self.discover_parser
    
    def _create_augment_chain(self):
        """검토를 마친 포인트를 적용하여 일기 증강"""
        return augment_template_v2 | self.gpt | self.augment_parser
    
    def augment_from_perspective(self, diary_entry: str, life_orientation: str) -> str:
        """주어진 관점에서 일기를 분석하고 증강"""
        try:
            life_orientations_desc = self.get_life_orientation_definition(life_orientation)
            life_orientations_highlight = self.get_life_orientation_highlights(life_orientation)

            # 1. 주어진 관점으로 재해석할 포인트 발견
            discovery_chain = self._create_discover_chain()
            
            discovery_result = discovery_chain.invoke({
                "diary_entry": diary_entry,
                "life_orientation": life_orientation,
                "life_orientation_desc": life_orientations_desc,
                "highlight": life_orientations_highlight,
                "format_instructions": self.discover_parser.get_format_instructions()
            })
            print("Discovery Result Type:", type(discovery_result))
            print("Discovery Result Content:", discovery_result)

            # discovery_result는 이미 DiscoveredResults 객체이므로
            # points 속성을 직접 사용하면 됩니다
            extracted_points = discovery_result.points

            # 2. 주어진 관점으로 일기 증강
            points = []
            for point in extracted_points:
                print("\n- ", point)
                points.append(point)
            
            points_str = "\n========\n".join([
                f"- Relevant excerpts: {j.quotes}\n- Interpretation: {j.new_perspective}" 
                for j in points
            ])
            print("====================\n발견된 부분: ", points_str)
            
            augment_chain = self._create_augment_chain()
            
            augmented_result = augment_chain.invoke({
                "diary_entry": diary_entry,
                "relevant_points": points_str,  # 문자열로 변환된 버전 사용
                "life_orientation": life_orientation,
                "highlight": life_orientations_highlight,
                "format_instructions": self.augment_parser.get_format_instructions()
            })
            print("====================\n", augmented_result.diary_entry)
            return augmented_result.diary_entry
            
        except Exception as e:
            raise Exception(f"증강 중 오류 발생: {str(e)}")

    def get_life_orientation_definition(self, life_orientation: str) -> str:
        """특정 관점의 설명을 반환"""
        if life_orientation not in self.life_orientations:
            raise ValueError(f"정의되지 않은 관점입니다: {life_orientation}")
        return self.life_orientations[life_orientation]['explanation_v2']

    def get_life_orientation_highlights(self, life_orientation: str) -> str:
        """특정 관점의 강조 사항을 반환"""
        if life_orientation not in self.life_orientations:
            raise ValueError(f"정의되지 않은 관점입니다: {life_orientation}")
        return self.life_orientations[life_orientation]['highlight']
    
    def get_life_orientations(self) -> List[str]:
        """모든 관점 목록 반환"""
        return list(self.life_orientations.keys())
