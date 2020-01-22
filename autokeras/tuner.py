import os

import kerastuner
import tensorflow as tf

from autokeras import const
from autokeras import oracle as oracle_module


class AutoTuner(kerastuner.engine.multi_execution_tuner.MultiExecutionTuner):
    """A Tuner class based on KerasTuner for AutoKeras.

    Different from KerasTuner's Tuner class. AutoTuner's not only tunes the
    Hypermodel which can be directly built into a Keras model, but also the
    preprocessors. Therefore, a HyperGraph stores the overall search space containing
    both the Preprocessors and Hypermodel. For every trial, the HyperGraph build the
    PreprocessGraph and KerasGraph with the provided HyperParameters.

    The AutoTuner uses EarlyStopping for acceleration during the search and fully
    train the model with full epochs and with both training and validation data.
    The fully trained model is the best model to be used by AutoModel.

    # Arguments
        **kwargs: The args supported by KerasTuner.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._finished = False

    # Override the function to prevent building the model during initialization.
    def _populate_initial_space(self):
        pass

    def get_best_model(self):
        model = super().get_best_models()[0]
        model.load_weights(self.best_model_path)
        return model

    def search(self,
               callbacks=None,
               fit_on_val_data=False,
               **fit_kwargs):
        """Search for the best HyperParameters.

        If there is not early-stopping in the callbacks, the early-stopping callback
        is injected to accelerate the search process. At the end of the search, the
        best model will be fully trained with the specified number of epochs.

        # Arguments
            callbacks: A list of callback functions. Defaults to None.
            fit_on_val_data: Boolean. Use the training set and validation set for the
                final fit of the best model.
        """
        if self._finished:
            return

        # Insert early-stopping for acceleration.
        if not callbacks:
            callbacks = []
        new_callbacks = self._deepcopy_callbacks(callbacks)
        if not any([isinstance(callback, tf.keras.callbacks.EarlyStopping)
                    for callback in callbacks]):
            new_callbacks.append(tf.keras.callbacks.EarlyStopping(patience=10))

        super().search(callbacks=new_callbacks, **fit_kwargs)

        # Fully train the best model with original callbacks.
        if not any([isinstance(callback, tf.keras.callbacks.EarlyStopping)
                    for callback in callbacks]) or fit_on_val_data:
            best_trial = self.oracle.get_best_trials(1)[0]
            best_hp = best_trial.hyperparameters
            fit_kwargs['callbacks'] = self._deepcopy_callbacks(callbacks)
            if fit_on_val_data:
                fit_kwargs['x'] = fit_kwargs['x'].concatenate(
                    fit_kwargs['validation_data'])
            model = self.hypermodel.build(best_hp)
            model.fit(**fit_kwargs)
        else:
            model = self.get_best_models()[0]

        model.save_weights(self.best_model_path)
        self._finished = True

    @property
    def best_model_path(self):
        return os.path.join(self.project_dir, 'best_model')


class RandomSearch(AutoTuner, kerastuner.RandomSearch):
    """KerasTuner RandomSearch with preprocessing layer tuning."""
    pass


class Hyperband(AutoTuner, kerastuner.Hyperband):
    """KerasTuner Hyperband with preprocessing layer tuning."""
    pass


class BayesianOptimization(AutoTuner, kerastuner.BayesianOptimization):
    """KerasTuner BayesianOptimization with preprocessing layer tuning."""
    pass


class Greedy(AutoTuner):

    def __init__(self,
                 hypermodel,
                 objective,
                 max_trials,
                 initial_hps=None,
                 seed=None,
                 hyperparameters=None,
                 tune_new_entries=True,
                 allow_new_entries=True,
                 **kwargs):
        self.seed = seed
        oracle = oracle_module.GreedyOracle(
            hypermodel=hypermodel,
            objective=objective,
            max_trials=max_trials,
            initial_hps=initial_hps,
            seed=seed,
            hyperparameters=hyperparameters,
            tune_new_entries=tune_new_entries,
            allow_new_entries=allow_new_entries)
        super().__init__(
            hypermodel=hypermodel,
            oracle=oracle,
            **kwargs)


class ImageClassifierTuner(Greedy):
    def __init__(self, **kwargs):
        super().__init__(
            initial_hps=const.INITIAL_HPS['image_classifier'],
            **kwargs)


TUNER_CLASSES = {
    'bayesian': BayesianOptimization,
    'random': RandomSearch,
    'hyperband': Hyperband,
    'greedy': Greedy,
    'image_classifier': ImageClassifierTuner,
    'image_regressor': Greedy,
    'text_classifier': Greedy,
    'text_regressor': Greedy,
    'structured_data_classifier': Greedy,
    'structured_data_regressor': Greedy,
}


def get_tuner_class(tuner):
    if isinstance(tuner, str) and tuner in TUNER_CLASSES:
        return TUNER_CLASSES.get(tuner)
    else:
        raise ValueError('The value {tuner} passed for argument tuner is invalid, '
                         'expected one of "greedy", "random", "hyperband", '
                         '"bayesian".'.format(tuner=tuner))
