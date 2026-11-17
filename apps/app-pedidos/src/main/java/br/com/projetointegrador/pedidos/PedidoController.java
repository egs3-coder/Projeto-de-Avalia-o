package br.com.projetointegrador.pedidos;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;

@RestController
@RequestMapping("/api/pedidos")
public class PedidoController {

    private static final Logger log = LoggerFactory.getLogger(PedidoController.class);

    private final PedidoService service;

    public PedidoController(PedidoService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Pedido criar(@RequestBody NovoPedido novo) {
        return service.criar(novo);
    }

    @GetMapping
    public List<Pedido> listar() {
        return service.listarRecentes();
    }

    @GetMapping("/{id}")
    public Pedido buscar(@PathVariable Long id) {
        return service.buscar(id);
    }

    /** Endpoint de teste: gera erro 5xx para os painéis de taxa de erro e para logs de erro. */
    @GetMapping("/erro")
    public void erro() {
        log.error("Erro simulado no app-pedidos (endpoint de teste /api/pedidos/erro)");
        throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "erro simulado");
    }
}
