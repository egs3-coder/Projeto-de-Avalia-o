package br.com.projetointegrador.estoque;

import jakarta.persistence.*;

@Entity
@Table(name = "produtos")
public class Produto {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String nome;

    @Column(nullable = false)
    private int quantidade;

    @Column(nullable = false)
    private int estoqueMinimo;

    protected Produto() {
    }

    public Produto(String nome, int quantidade, int estoqueMinimo) {
        this.nome = nome;
        this.quantidade = quantidade;
        this.estoqueMinimo = estoqueMinimo;
    }

    public Long getId() { return id; }
    public String getNome() { return nome; }
    public int getQuantidade() { return quantidade; }
    public int getEstoqueMinimo() { return estoqueMinimo; }
    public void setQuantidade(int quantidade) { this.quantidade = quantidade; }
}
