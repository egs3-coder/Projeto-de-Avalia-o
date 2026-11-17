package br.com.projetointegrador.estoque;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;

@RestController
@RequestMapping("/api/produtos")
public class ProdutoController {

    private static final Logger log = LoggerFactory.getLogger(ProdutoController.class);

    private final EstoqueService service;

    public ProdutoController(EstoqueService service) {
        this.service = service;
    }

    @GetMapping
    public List<Produto> listar() {
        return service.listar();
    }

    @GetMapping("/{id}")
    public Produto buscar(@PathVariable Long id) {
        return service.buscar(id);
    }

    /** Chamado pelo app-pedidos para baixar o estoque de um produto. */
    @PostMapping("/{id}/reservar")
    public Produto reservar(@PathVariable Long id, @RequestParam int quantidade) {
        log.debug("Requisição de reserva: produto={}, quantidade={}", id, quantidade);
        return service.reservar(id, quantidade);
    }

    @PostMapping("/{id}/repor")
    public Produto repor(@PathVariable Long id, @RequestParam int quantidade) {
        return service.repor(id, quantidade);
    }

    /** Endpoint de teste: gera erro 5xx para os painéis de taxa de erro e para logs de erro. */
    @GetMapping("/erro")
    public void erro() {
        log.error("Erro simulado no app-estoque (endpoint de teste /api/produtos/erro)");
        throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "erro simulado");
    }
}
