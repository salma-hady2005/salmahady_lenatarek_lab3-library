USE library_db;

-- Insert at least 3 authors
INSERT INTO AUTHOR (name, country) VALUES
('Naguib Mahfouz', 'Egypt'),
('William Shakespeare', 'England'),
('Jane Austen', 'England');

-- Insert at least 6 books
INSERT INTO BOOK (title, price, author_id) VALUES
('Palace Walk', 250.00, 1),
('The Thief and the Dogs', 180.00, 1),
('Hamlet', 200.00, 2),
('Macbeth', 175.00, 2),
('Pride and Prejudice', 220.00, 3),
('Emma', 190.00, 3);
SELECT * FROM AUTHOR;

SELECT * FROM BOOK;