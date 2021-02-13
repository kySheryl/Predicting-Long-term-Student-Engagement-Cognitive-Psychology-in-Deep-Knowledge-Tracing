# Predicting-Long-term-Student-Engagement-Cognitive-Psychology-in-Deep-Knowledge-Tracing
This project predicts the number of sessions a student will practice/study in the next module based on his/her performance and interaction in the previous modules.

## What is in this repository?
This repository includes implementation of two models on the problem, an LSTM-based model, where the final dense layer leverages summation of LSTM outputs, and a transformer-based architecture with stacked encoders, composed of self-attention layers and feed-forward networks. Both .ipynb and .py versions are provided.


## Dataset

The model was trained on a psychology MOOC dataset [1] that contains students-module interactions on Coursera. The raw data is collected from a psychology course offered through Coursera. A total of 5615 students signed up for the course and agreed to have their data included for research purposes. The course was comprised of 11 modules. Each module consisted of online textbook and video lectures. Students were expected to watch video lectures and complete the related online textbook of the module every week. A multiple-choice quiz was released to test students on the module concepts on the Friday of each week with the exception of the final week, where there was a final exam instead. We use the data from the 747 students who completed the course (i.e., completed the final exam). 639 of those students completed all 11 quizzes and all 747 students completed at least one of the quizzes.

We directly make use of the processed data [1] which is available here. (https://github.com/pcarvalh/Self-regulated-spacing-online-class)

## References

[1] Carvalho, P.F., Sana, F. & Yan, V.X. Self-regulated spacing in a massive open online course is related to better learning. npj Sci. Learn. 5, 2 (2020). https://doi.org/10.1038/s41539-020-0061-1
