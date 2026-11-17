package br.com.projetointegrador.estoque;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface ProdutoRepository extends JpaRepository<Produto, Long> {

    @Query("select count(p) from Produto p where p.quantidade < p.estoqueMinimo")
    long contarAbaixoDoMinimo();

    @Query("select coalesce(sum(p.quantidade), 0) from Produto p")
    long somarUnidades();
}
