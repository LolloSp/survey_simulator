"""Modalità CATI e CAPI: dialogo fra intervistatore e rispondente (M8)."""

from synthsurvey.config.schema import SynthSurveyConfig
from synthsurvey.interview.session import InterviewResult, InterviewSpec
from synthsurvey.llm.pool import LLMPool
from synthsurvey.questionnaire.modes import ModeQuestionnaire
from synthsurvey.questionnaire.schema import Questionnaire


async def run_dialogue(
    spec: InterviewSpec,
    questionnaire: Questionnaire,
    mode_questionnaire: ModeQuestionnaire,
    pool: LLMPool,
    config: SynthSurveyConfig,
) -> InterviewResult:
    raise NotImplementedError("le modalità CATI e CAPI arrivano con la milestone M8")
