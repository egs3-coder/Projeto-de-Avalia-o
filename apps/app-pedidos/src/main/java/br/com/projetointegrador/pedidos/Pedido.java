package br.com.projetointegrador.pedidos;

import jakarta.persistence.*;

import java.time.Instant;

@Entity
@Table(name = "pedidos")
public class Pedido {

    public enum Status { APROVADO, REJEITADO }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private Long produtoId;

    @Column(nullable = false)
    private int quantidade;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private Status status;

    @Column(nullable = false)
    private Instant criadoEm;

    protected Pedido() {
    }

    public Pedido(Long produtoId, int quantidade, Status status) {
        this.produtoId = produtoId;
        this.quantidade = quantidade;
        this.status = status;
        this.criadoEm = Instant.now();
    }

    public Long getId() { return id; }
    public Long getProdutoId() { return produtoId; }
    public int getQuantidade() { return quantidade; }
    public Status getStatus() { return status; }
    public Instant getCriadoEm() { return criadoEm; }
}
