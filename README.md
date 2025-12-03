<p align="center">
  <img src="https://github.com/Binivert/security-system/blob/main/assets/unnamed.jpg" width="400">
</p>

# 🎬 Movie Recommendation System

This project is a movie recommendation system that helps you find movies that you might like. It uses a content-based filtering algorithm that compares movies based on their features, such as genres, keywords, cast, crew, and overview. It also has a web interface that lets you search, rate, and get recommendations for movies. 🙌

## 🛠 Installation and Usage

To run this project, you need to have Python 3 and some libraries installed. You also need to download two datasets: MovieLens and TMDB. 
To run the project, follow these steps:

1. Clone or download this repository to your computer. 💻
2. Go to the project folder and run `python preprocess.py` to prepare the data. 📊
3. Run `python app.py` to start the web application. 🚀
4. Search for movies, rate them, and get recommendations. 🌟

## 🧠 How it Works

This project uses a content-based filtering algorithm that recommends movies that are similar to the ones that you like or have rated highly. It does this by calculating the similarity between movies based on their features, such as genres, keywords, cast, crew, and overview. It uses the TF-IDF technique to vectorize the features and the cosine similarity to measure the similarity. 📐

The project also uses Flask, a web framework for Python, to create a web interface that connects to the TMDB API to get the details and images of the movies. It also allows you to rate the movies and store your ratings in a dictionary. ⭐

## 🙏 Acknowledgements

This project is based on the tutorial from [TechVidvan] 🙏

## 💬 Feedback and Collaboration

I hope you find this project useful and interesting. If you have any feedback, questions, or suggestions, please feel free to contact me at itsbini7@gmail.com. You can also follow me on instagram or LinkedIn.

If you want to contribute to this project, you are welcome to fork this repository and make a pull request. Some possible improvements or extensions are:

- Adding a user login and registration system to store and retrieve user ratings and preferences 🔐
- Implementing a hybrid recommendation system that combines content-based and collaborative filtering methods 🤝
- Adding more features or data sources to improve the accuracy and diversity of the recommendations 🌈
- Improving the design and functionality of the web interface 💅
