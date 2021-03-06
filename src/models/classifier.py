import os
import pickle
import faiss
import fasttext
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.preprocessing import MultiLabelBinarizer, normalize
from sklearn.metrics import precision_score, recall_score, f1_score


# Add a logger
class PredictError(Exception):
    def __init__(self, text):
        self.txt = text


class Classifier:
    start_model_status = 0
    vec_size = 300
    y = np.array([])
    emb = {}

    def __init__(self, model: str, faiss_path: str = None, embedding_path: str = None):
        """
        :param model: Путь до модели построения эмбэдингов.
        :param faiss_path: Путь до сохранённых индексов faiss.
        :param embedding_path: Путь до сохранённых вектороных представлений фраз.
        """
        self.model = fasttext.load_model(str(self.path(model)))
        if faiss_path:
            with open(self.path(faiss_path), 'rb') as f:
                self.index, self.y = pickle.load(f)
                self.start_model_status = 1
        if embedding_path:
            with open(self.path(embedding_path), 'rb') as f:
                self.emb = pickle.load(f)

    @staticmethod
    def path(path):
        return Path(os.getcwd(), path)

    def embeddings(self, texts: list or np.array) -> np.array:
        """
        Построение векторынх представлений для фраз.
        :param texts: Набор фраз.
        :return: Набор векторов.
        """
        emb = []
        for text in texts:
            text = text.replace('-', ' ').lower().strip()
            if not self.emb.get(text, np.array([])).shape[0]:
                self.emb[text] = normalize([self.model.get_sentence_vector(text)])[0]
            emb.append(self.emb.get(text))
        with open(self.path('models/cache/emb.pkl'), 'wb') as f:
            pickle.dump(self.emb, f)
        return np.array(emb, dtype='float32')

    def add(self, x: np.array, y: np.array):
        """
        Добавление фраз в индекс и сохранение текущего состояния модели.
        :param x: Набор фраз.
        :param y: Набор категорий.
        :return: self.
        """
        if not self.y.shape[0]:
            self.index = faiss.IndexFlat(self.vec_size)
        if not self.start_model_status:
            self.index.add(self.embeddings(x))
            self.y = np.append(self.y, y)
            with open(self.path('models/cache/faiss.pkl'), 'wb') as f:
                pickle.dump((self.index, self.y), f)
        return self

    @staticmethod
    def __get_top_classes(classes: np.array, max_count: int = 10) -> list:
        '''
        Возвращает n-e количество предсказанных классов моделью.
        :param classes: Классы из которых небходимо выбрать топ n.
        :param max_count: Максимальное количество возвращаемых классов.
        :return: Список классов для текущего объекта.
        '''
        unique = set()
        for subtopic in classes:
            unique = unique.union(set(subtopic))
            if len(unique) >= max_count:
                break
        return list(unique)[:max_count]

    def predict(self, x: np.array, limit: float) -> tuple:
        """
        Предсказание категории для фразы.
        :param x: Набор фраз.
        :param limit: Допустимая дистанция.
        :return: Словарь из двух элементов (predict_limit, all_predict),
        где predict_limit - это индексы объектов, которые прдесказаны по дистанции,
        all_predict - масиив, который для фразы содержит список катеогрий.
        """
        predict_limit, all_predict = [], []
        dis, ind = self.index.search(self.embeddings(x), k=25)
        for i in range(x.shape[0]):
            if any(dis[i] <= 1 - limit):  # We save indexes where the models is not sure
                predict_limit.append(i)
                # Consider the weighted confidence of classes
                all_predict.append(self.__get_top_classes(self.y[ind[i][dis[i] <= 1 - limit]]))
            else:
                all_predict.append(self.__get_top_classes(self.y[ind[i]]))
        return np.array(predict_limit), np.array(all_predict, dtype='object')

    @staticmethod
    def metrics(y_true: np.array, y_pred: np.array, average: str = 'samples') -> pd.DataFrame:
        """
        Метод выполняет подсчёт метрик.
        :param y_true: Истинное значение целевой переменной.
        :param y_pred: Предсказанное значение целевой переменной.
        :param average: Метод подсчёта метрик.
        :return: Результаты метрик в формате pd.DataFrame.
        """
        classes = set()  # Отбор уникальных классов
        for i in range(y_true.shape[0]):
            classes = classes | set(y_true[i]) | set(y_pred[i])
        average = 'weighted' if len(classes) == 1 else average

        mlb = MultiLabelBinarizer(classes=list(classes))
        y_true = mlb.fit_transform(y_true)
        y_pred = mlb.transform(y_pred)
        return pd.DataFrame({
            'f1': [f1_score(y_true, y_pred, average=average)],
            'precision': [precision_score(y_true, y_pred, average=average, zero_division=1)],
            'recall': [recall_score(y_true, y_pred, average=average, zero_division=0)],
            'validation_size': [y_true.shape[0]]
        })
