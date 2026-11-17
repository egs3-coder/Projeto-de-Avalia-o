package br.com.projetointegrador.pedidos;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface PedidoRepository extends JpaRepository<Pedido, Long> {
    List<Pedido> findTop50ByOrderByIdDesc();
}
