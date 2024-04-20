const express = require("express");

const app = express(); // Исправлено объявление переменной

const port = 3000;

// Подключение статических файлов из папки "docs"
app.use(express.static(__dirname + "/docs"));

// Обработчик маршрута для главной страницы
app.get("/", (req, res) => {
    res.sendFile(__dirname + "/index.html");
});

// Обработчик маршрута для страницы editVideo.html
app.get("/editVideo.html", (req, res) => {
    res.sendFile(__dirname + "/editVideo.html");
});

// Запуск сервера на порту 3000
app.listen(port, () => {
    console.log(`Example app listening at http://localhost:${port}`);
});
