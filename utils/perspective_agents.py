from langchain.prompts import PromptTemplate
from langchain_community.chat_models import ChatOpenAI
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from typing import Dict, List
import json
from pathlib import Path

# 추출 결과 모델 정의
class DiscoveringSteps(BaseModel):
    point: str = Field(description="A positive or grateful point.")
    quotes: str = Field(description="A sentence from the original diary entry that reveals a positive or grateful life_orientation.")
    reason: str = Field(description="A reason why this is something to be positive or grateful, including the life_orientation used.")
class DiscoveredResults(BaseModel):
    points: list[DiscoveringSteps] = Field(description="List of extracted positives or things to be grateful for")
# 판정 결과 모델 정의
class JudgmentResult(BaseModel):
    point: DiscoveringSteps
    is_relevant: bool = Field(description="Whether the point aligns with the given life_orientation.")
    reasoning: str = Field(description="Reason why the point is or is not relevant.")
# 증강 결과 모델 정의
class AugmentResult(BaseModel):
    diary_entry: str = Field(description="증강된 일기 내용")


# 프롬프트 템플릿 정의
extract_template = PromptTemplate(
    input_variables=["entry", "life_orientation"],
    template=(
        """
        당신은 {life_orientation}인 삶의 태도를 갖고 있는 사람입니다.
        주어진 글을 당신의 일기라고 생각하고 읽고, 드러난 사건이나 일어난 일, 느낀 감정이나 들었던 생각 중에서 좀 더 긍정적이거나 감사하게 바라볼 수 있는 부분을 찾으세요.
        {life_orientation}인 태도가 드러나는 부분을 찾는 것이 아니라, 미처 인지하지 못하는 하루의 좋은 점을 찾는 데에 목적이 있다는 것에 유념하세요!

        Diary Entry:
        {diary_entry}

        Extract points following these criteria:
        1. 일기를 통해 알 수 있는 하루동안 있었던 일들 중에서 긍정적으로 여길 수 있거나 감사할 수 있는 부분을 찾아내세요.
        2. 일기 항목의 특정 부분을 참조하세요.
        3. 주어진 관점에 기반해서 왜 해당 부분을 다르게 바라볼 필요가 있는지 이유를 제공하세요.

        한국어로 응답하세요.
        {format_instructions}
        """
    )
)

# 두 번째 프롬프트 템플릿: 관점 판정
discover_template = PromptTemplate(
    input_variables=["points", "life_orientation", "life_orientation_desc"],
    template=(
        """
        당신은 {life_orientation}인 삶의 태도를 갖고 있습니다. 
        구체적으로 '{life_orientation}' 삶의 태도는 다음을 의미합니다.: "{life_orientation_desc}"
        
        {life_orientation} 관점에서 사용자의 하루를 좀 더 긍정적이거나 감사한 관점에서 볼 수 있는 포인트를 찾아냈습니다.
        당신이 보기에 발견된 포인트가 이 '{life_orientation}' 관점 기반인지 평가하세요.
        사용자가 거부감을 느낄 수 있으니, 실제로 하루에 일어난 일에 비해 너무 지나친 해석이지는 않은지 주의하여 살펴보세요.

        평가할 포인트:
        {point_json}

        이 긍정적/감사한 점이 '{life_orientation}' 관점과 관련이 있고 적절한지 판단하고 그 이유를 설명하세요.

        한국어로 응답하세요.
        {format_instructions}
        """
    )
)

# 세 번째 프롬프트 템플릿: 내용 증강
augment_template = PromptTemplate(
    input_variables=["diary_entry", "life_orientation", "relevant_points"],
    template=(
        """
        당신은 글쓰기 전문가입니다. 
        사용자가 작성한 일기에서 {life_orientation} 관점에서 하루를 좀 더 긍정적이거나 감사한 관점에서 볼 수 있는 포인트를 발견했습니다.
        일기 작성자가 {life_orientation} 관점에서 자신의 하루의 좋은 측면을 더 생각할 수 있도록, 발견된 포인트를 바탕으로 일기 내용을 증강해 주세요.

        원본 일기:
        {diary_entry}

        발견된 의미있는 부분들:
        {relevant_points}

        다음 기준으로 일기를 증강해주세요:
        1. 의미있는 관점들을 원본 일기에 최대한 자연스럽게 적용할 것.
        2. 없는 사실을 지어내지 말 것.
        3. 내용의 증강은 발견된 긍정적/감사할 포인트의 '이유'를 참고할 것.
        4. '긍정적', '감사한'과 같은 직접적인 표현은 전반적인 글의 내용에 비해 너무 과하지 않을 때만 사용할 것.

        한국어로 응답하세요.
        {format_instructions}
        """
    )
)



class PerspectiveManager:
    def __init__(self, api_key: str):
        self.life_orientations = self._load_life_orientations()
        self.llm = ChatOpenAI(
            model_name="gpt-4o-mini",
            temperature=0.7,
            openai_api_key=api_key
        )
        self.extract_parser = PydanticOutputParser(pydantic_object=DiscoveredResults)
        self.discover_parser = PydanticOutputParser(pydantic_object=JudgmentResult)
        self.augment_parser = PydanticOutputParser(pydantic_object=AugmentResult)
    
    
    def _load_life_orientations(self) -> Dict:
        """life_orientations.json 파일에서 관점 정의를 로"""
        json_path = Path(__file__).parent.parent / 'config' / 'life_orientations.json'
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _create_extract_chain(self):
        """긍정적/감사한 포인트를 발견하는 체인 생성"""
        return extract_template | self.llm | self.extract_parser
    
    def _create_discover_chain(self):
        """발견된 포인트의 관련성을 판단하는 체인 생성"""
        return discover_template | self.llm | self.discover_parser
    
    def _create_augment_chain(self):
        """검토를 마친 포인트를 적용하여 일기 증강"""
        return augment_template | self.llm | self.augment_parser
    
    def augment_from_perspective(self, diary_entry: str, life_orientation: str, value: str) -> str:
        """주어진 관점에서 일기를 분석하고 증강"""
        try:
            # 1. 긍정적/감사한 포인트 발견
            discovery_chain = self._create_discovery_chain()
            discovery_result = discovery_chain.invoke({
                "diary_entry": diary_entry,
                "life_orientation": life_orientation,
                "value": value,
                "format_instructions": self.discovery_parser.get_format_instructions()
            })
            print("Discovery Result Type:", type(discovery_result))
            print("Discovery Result Content:", discovery_result)

            # discovery_result는 이미 DiscoveredResults 객체이므로
            # points 속성을 직접 사용하면 됩니다
            extracted_points = discovery_result.points

            # 2. 각 포인트에 대한 관점 기반 판단
            judgment_chain = self._create_judgment_chain()
            life_orientations_desc = self.get_life_orientation_definition(life_orientation)
            
            judgments = []
            for point in extracted_points:
                print("\n각각: ", point.point)
                judgment = judgment_chain.invoke({
                    "life_orientation": life_orientation,
                    "life_orientation_desc": life_orientations_desc,
                    "point_json": point.model_dump_json(),
                    "format_instructions": self.judgment_parser.get_format_instructions()
                })
                print("결과: ", judgment.is_relevant)
                judgments.append(judgment)
            
            # 3. 관련성 있는 포인트들로 일기 증강
            relevant_points_str = "\n".join([
                f"- 포인트: {j.point.point}\n  이유: {j.point.reason} 원문: {j.point.quotes}" 
                for j in judgments if j.is_relevant
            ])
            print("====================\n최종 선정: ", relevant_points_str)
            
            augment_chain = self._augment_diary_chain()
            augmented_result = augment_chain.invoke({
                "diary_entry": diary_entry,
                "relevant_points": relevant_points_str,  # 문자열로 변환된 버전 사용
                "life_orientation": life_orientation,
                "format_instructions": self.augment_parser.get_format_instructions()
            })
            return augmented_result.diary_entry
            
        except Exception as e:
            raise Exception(f"증강 중 오류 발생: {str(e)}")

    def get_life_orientation_definition(self, life_orientation: str) -> str:
        """특정 관점의 설명을 반환"""
        if life_orientation not in self.life_orientations:
            raise ValueError(f"정의되지 않은 관점입니다: {life_orientation}")
        return self.life_orientations[life_orientation]['definition']
    
    def get_life_orientations(self) -> List[str]:
        """모든 관점 목록 반환"""
        return list(self.life_orientations.keys())
