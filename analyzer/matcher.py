from abc import ABC, abstractmethod


class JobMatcher(ABC):

    @abstractmethod
    def analyze(self, job, profile):
        pass