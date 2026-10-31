-- Dados de exemplo para o serviço postgres-demo.
CREATE TABLE regioes (id SERIAL PRIMARY KEY, nome TEXT NOT NULL);
INSERT INTO regioes (nome) VALUES ('Norte'), ('Nordeste'), ('Centro-Oeste'), ('Sudeste'), ('Sul');

CREATE TABLE vendas (
    id SERIAL PRIMARY KEY,
    data DATE NOT NULL,
    regiao_id INT NOT NULL REFERENCES regioes(id),
    produto TEXT NOT NULL,
    quantidade INT NOT NULL,
    valor NUMERIC(12, 2) NOT NULL
);

INSERT INTO vendas (data, regiao_id, produto, quantidade, valor)
SELECT
    DATE '2024-01-01' + (random() * 365)::int,
    1 + (random() * 4)::int,
    (ARRAY['Notebook', 'Monitor', 'Teclado', 'Mouse', 'Headset'])[1 + (random() * 4)::int],
    1 + (random() * 9)::int,
    round((50 + random() * 4950)::numeric, 2)
FROM generate_series(1, 2000);

-- Usuário somente leitura recomendado para a aplicação.
CREATE ROLE leitor LOGIN PASSWORD 'leitor';
GRANT USAGE ON SCHEMA public TO leitor;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO leitor;
