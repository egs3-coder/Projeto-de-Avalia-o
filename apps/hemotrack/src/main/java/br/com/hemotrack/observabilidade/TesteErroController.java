package br.com.hemotrack.observabilidade;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/**
 * Endpoint de teste da observabilidade: gera um erro HTTP 500 de proposito, para os paineis de
 * taxa de erro, os logs de nivel ERROR no Loki e os traces com erro no Tempo.
 * Fica sob /api (fora do login, como a API do sensor).
 */
@RestController
public class TesteErroController {

    private static final Logger LOG = LoggerFactory.getLogger(TesteErroController.class);

    @GetMapping("/api/teste/erro")
    public void erro() {
        LOG.error("Erro simulado no HemoTrack (endpoint de teste /api/teste/erro)");
        throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "erro simulado");
    }
}
