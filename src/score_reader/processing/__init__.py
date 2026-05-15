from .csv_export import write_score_sheet_csv

__all__ = ["ScoreSheetParser", "write_score_sheet_csv"]


def __getattr__(name: str):
    if name == "ScoreSheetParser":
        from .score_sheet_parser import ScoreSheetParser

        return ScoreSheetParser
    raise AttributeError(name)
