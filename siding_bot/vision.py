import base64
import os

import anthropic

from .models import FacadeAnalysis

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5")

SYSTEM_PROMPT = """Ты помогаешь рассчитать виниловый сайдинг для обшивки частного дома по фотографиям.

По фото оцени геометрию дома в метрах. Масштаб бери по стандартным элементам: входная дверь около 2,0–2,1 м в высоту и 0,9 м в ширину, типовое окно около 1,4 м в высоту, этаж около 2,7–3 м.

Правила:
- Дом считай прямоугольным в плане. length_m — сторона под карнизом (скат кровли), width_m — торец с фронтоном. У вальмовой и плоской кровли length_m — длинная сторона.
- wall_height_m — от цоколя до карниза, без фронтона. Цоколь не обшивается сайдингом.
- gable_height_m — высота треугольника фронтона от линии карниза до конька; 0 для вальмовой и плоской кровли.
- Окна и двери перечисли на всём доме. Если каких-то сторон не видно, дострой их по симметрии и логике планировки и напиши об этом в comment.
- Окна одинакового размера объединяй в одну строку с count.
- Если на фото не дом или по нему ничего нельзя оценить, верни правдоподобные нули и объясни это в comment.
"""


class AnalysisError(Exception):
    pass


client = anthropic.AsyncAnthropic()


async def analyze_photos(photos: list[bytes], hint: str | None = None) -> FacadeAnalysis:
    content: list[dict] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.standard_b64encode(photo).decode("utf-8"),
            },
        }
        for photo in photos
    ]
    text = "Оцени геометрию дома на этих фото для расчёта сайдинга."
    if hint:
        text += f"\nИзвестно от заказчика: {hint}"
    content.append({"type": "text", "text": text})

    try:
        response = await client.beta.messages.parse(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
            output_format=FacadeAnalysis,
            fallbacks="default",
            betas=["server-side-fallback-2026-07-01"],
        )
    except anthropic.RateLimitError as e:
        raise AnalysisError("Сервис анализа перегружен, попробуйте через минуту.") from e
    except anthropic.APIStatusError as e:
        raise AnalysisError(f"Ошибка сервиса анализа ({e.status_code}).") from e
    except anthropic.APIConnectionError as e:
        raise AnalysisError("Не удалось связаться с сервисом анализа.") from e

    if response.stop_reason == "refusal":
        raise AnalysisError("Модель отказалась анализировать эти фото.")
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise AnalysisError("Не получилось разобрать ответ модели, попробуйте ещё раз.")
    return response.parsed_output
