import os
import pandas as pd
import numpy as np
import faiss
from time import time
from pathlib import Path
from src.models import Classifier
from sklearn.model_selection import LeaveOneOut


class LeaveClassifier(Classifier):
    def __init__(self, fasttext_model: str, faiss_path: str):
        super(LeaveClassifier, self).__init__(fasttext_model, faiss_path)

    def add(self, x: np.array, y: np.array):
        self.index = faiss.IndexFlat(300)
        self.index.add(self.embeddings(x))
        self.y = np.append(self.y, y)
        return self


class Stratified:
    def __init__(self, train_file: str, classifier: Classifier):
        self.classifier = classifier
        self.train = self.__read_train(train_file)

    def __read_train(self, train_file: str):
        train = pd.read_csv(self.path(train_file)).sort_values('frequency', ascending=False)[['phrase', 'subtopic']]
        train['true'] = train['subtopic']
        return train.groupby(by='phrase').agg(subtopic=('subtopic', 'unique'), true=('true', 'unique')).reset_index()

    @staticmethod
    def path(path):
        return Path(os.getcwd(), path)

    def run(self, limit: float):
        loo = LeaveOneOut()
        predicts, all_metrics = pd.DataFrame(), pd.DataFrame()

        for train_indices, test_index in loo.split(self.train):
            train, test = self.train.iloc[train_indices], self.train.iloc[test_index]

            self.classifier.add(train['phrase'].values, train['subtopic'].values)

            # Снятие метрик
            index_limit, all_predict = self.classifier.predict(test['phrase'].values, limit)
            predict = pd.DataFrame({'phrase': test.phrase, 'subtopic': all_predict.tolist(), 'true': test['true']})
            metrics = self.classifier.metrics(test['true'].values, all_predict)
            metrics['phrase'] = test.phrase.values

            # Объединение данных
            predicts = pd.concat([predicts, predict.explode('subtopic').explode('true')], ignore_index=True)
            all_metrics = pd.concat([all_metrics, metrics], ignore_index=True)

        # Сохранение данных
        all_metrics.to_csv(self.path(f'data/models/{limit}_all_metrics.csv'), index=False)
        predicts.to_csv(self.path(f'data/models/{limit}_predicts.csv'), index=False)


if __name__ == '__main__':
    classifier = LeaveClassifier('interim/adaptation/new_not_lem.bin', 'models/classifier.pkl')
    system = Stratified('data/processed/perfumery_train.csv', classifier)
    t1 = time()
    system.run(limit=0.9)
    print(time() - t1)