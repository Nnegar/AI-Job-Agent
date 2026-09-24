from abc import ABC, abstractmethod


class LLMAnalyzer(ABC):

    @abstractmethod
    def analyze_job(self, job, profile):
        pass
